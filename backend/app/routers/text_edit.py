"""
Phase 3 text-edit logic.

POST /api/sejda/preflight-edit  — font-tier + overflow check (no output PDF).
apply_text_edits()              — called from sejda.py apply pipeline (step 4).

Apply order per page:
  1. Collect per-line redact rects for all edits on the page.
  2. add_redact_annot() + apply_redactions(images=NONE, graphics=NONE) once.
  3. Re-insert new text via fitz.TextWriter (handles multi-run, mixed colour).
"""
from __future__ import annotations

import json
from typing import Any

import fitz
import pymupdf_fonts
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.font_resolver import FontResolution, resolve_font

router = APIRouter()

MAX_FILE_MB = 50
SHRINK_MIN_S = 0.70
SHRINK_STEP = 0.02
SHRINK_MIN_SIZE_PT = 6.0


# ── Font registration cache ───────────────────────────────────────────────────

def _register_font(page: fitz.Page, res: FontResolution) -> None:
    """Register a font with the page (safe to call multiple times)."""
    if res.fontbuffer:
        try:
            page.insert_font(fontname=res.fontname, fontbuffer=res.fontbuffer)
        except Exception:
            pass  # already registered
    # Base-14 fonts need no registration


def _get_fitz_font(res: FontResolution) -> fitz.Font:
    if res.fontbuffer:
        return fitz.Font(fontbuffer=res.fontbuffer)
    return fitz.Font(res.fontname)


# ── Overflow / shrink ─────────────────────────────────────────────────────────

def _runs_total_width(
    runs: list[dict[str, Any]],
    dom_size: float,
    font: fitz.Font,
    s: float,
) -> float:
    total = 0.0
    for run in runs:
        text = run.get("text", "")
        if not text:
            continue
        fs = dom_size * float(run.get("sizeScale", 1.0)) * s
        total += font.text_length(text, fontsize=fs)
    return total


def _find_shrink_scale(
    runs: list[dict[str, Any]],
    dom_size: float,
    available_width: float,
    font: fitz.Font,
) -> float:
    """
    Step s from 1.0 down in SHRINK_STEP increments.
    Dual floor: s >= SHRINK_MIN_S  AND  s * dom_size >= SHRINK_MIN_SIZE_PT.
    Returns the first s where text fits; if nothing fits within the floors,
    returns the smallest floor-compliant s (caller should warn and overflow).
    """
    steps = int(round((1.0 - SHRINK_MIN_S) / SHRINK_STEP))
    last_valid_s = 1.0  # smallest s that satisfies both floor conditions
    for i in range(steps + 1):
        s = round(1.0 - i * SHRINK_STEP, 6)
        if s < SHRINK_MIN_S:
            break
        if s * dom_size < SHRINK_MIN_SIZE_PT:
            break
        last_valid_s = s
        if _runs_total_width(runs, dom_size, font, s) <= available_width:
            return s
    return last_valid_s


def _extract_all_text(runs: list[dict[str, Any]]) -> str:
    return "".join(r.get("text", "") for r in runs)


# ── Span / line helpers ───────────────────────────────────────────────────────

def _build_span_lookup(raw: dict[str, Any], page_id: str) -> dict[str, dict[str, Any]]:
    """Build spanId → rawdict span mapping."""
    lookup: dict[str, dict[str, Any]] = {}
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        block_num = block.get("number", 0)
        for line_idx, line in enumerate(block.get("lines", [])):
            for span_idx, span in enumerate(line.get("spans", [])):
                span_id = f"{page_id}:{block_num}:{line_idx}:{span_idx}"
                lookup[span_id] = span
    return lookup


def _line_rect_from_span_ids(
    span_ids: list[str],
    raw: dict[str, Any],
) -> list[list[float]]:
    """
    Return per-line expanded bboxes for redaction.
    Expanded by ascender/descender so the redaction cleanly covers the ink.
    """
    # Parse exact (block, line, span) keys. Redacting the whole source line
    # erases neighboring table cells and bilingual translations that merely
    # share a baseline with the edited value.
    selected: dict[tuple[int, int], set[int]] = {}
    for sid in span_ids:
        parts = sid.rsplit(":", 3)
        if len(parts) == 4:
            try:
                key = (int(parts[1]), int(parts[2]))
                selected.setdefault(key, set()).add(int(parts[3]))
            except (ValueError, IndexError):
                pass

    rects: list[list[float]] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        block_num = int(block.get("number", 0))
        for li, line in enumerate(block.get("lines", [])):
            selected_indices = selected.get((block_num, li))
            if not selected_indices:
                continue
            line_spans = [
                span
                for span_idx, span in enumerate(line.get("spans", []))
                if span_idx in selected_indices
            ]
            if not line_spans:
                continue

            max_asc = 0.0
            max_desc = 0.0
            span_bboxes = [list(span.get("bbox", [0, 0, 0, 0])) for span in line_spans]
            baseline_y = max(float(bbox[3]) for bbox in span_bboxes)

            for span in line_spans:
                size = float(span.get("size", 12))
                asc_raw = float(span.get("ascender", 0.83))
                desc_raw = abs(float(span.get("descender", -0.21)))
                max_asc = max(max_asc, abs(asc_raw) * size)
                max_desc = max(max_desc, desc_raw * size)
                origin = span.get("origin")
                if origin:
                    baseline_y = float(origin[1])

            expanded = [
                min(bbox[0] for bbox in span_bboxes) - 0.5,
                min(min(bbox[1] for bbox in span_bboxes), baseline_y - max_asc),
                max(bbox[2] for bbox in span_bboxes) + 0.5,
                max(max(bbox[3] for bbox in span_bboxes), baseline_y + max_desc),
            ]
            rects.append(expanded)

    return rects


# ── TextWriter insertion ──────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str | None) -> tuple[float, float, float]:
    if not hex_color:
        return (0.0, 0.0, 0.0)
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r / 255.0, g / 255.0, b / 255.0)
    except ValueError:
        return (0.0, 0.0, 0.0)


def _write_runs(
    page: fitz.Page,
    runs: list[dict[str, Any]],
    dom_size: float,
    s: float,
    font: fitz.Font,
    start_x: float,
    start_y: float,
    right_x: float,
    line_height: float,
    overflow_policy: str,
) -> None:
    """
    Place text runs using fitz.TextWriter, with simple word-level line wrapping.
    start_y is the baseline of the first line.

    PyMuPDF ≥1.24 removed 'color' from TextWriter.append() — it moved to
    write_text(page, color=...).  We use one TextWriter per unique color so
    each writer can be flushed with its own color.
    """
    # color-tuple → TextWriter
    writers: dict[tuple[float, float, float], fitz.TextWriter] = {}

    x = start_x
    y = start_y

    for run in runs:
        text = run.get("text", "")
        if not text:
            continue
        fs = dom_size * float(run.get("sizeScale", 1.0)) * s
        color = _hex_to_rgb(run.get("color", "#000000"))

        tokens = _tokenize(text)
        for token in tokens:
            token_w = font.text_length(token, fontsize=fs)
            # Soft-wrap: if adding this token would overflow and we're not at line start
            if x + token_w > right_x + 0.5 and x > start_x:
                x = start_x
                y += line_height
            # Hard-wrap for a single token that exceeds the whole line
            if x + token_w > right_x + 0.5 and x == start_x:
                if overflow_policy == "truncate":
                    for end in range(len(token), 0, -1):
                        if font.text_length(token[:end], fontsize=fs) <= right_x - start_x:
                            token = token[:end]
                            token_w = font.text_length(token, fontsize=fs)
                            break
                    else:
                        continue
                # else: overflow — place anyway

            if color not in writers:
                writers[color] = fitz.TextWriter(page.rect)
            result = writers[color].append(fitz.Point(x, y), token, font=font, fontsize=fs)
            # result is (Rect, Point); Point.x is the end of this token
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                x = result[1].x
            else:
                x += token_w

    for color, tw in writers.items():
        tw.write_text(page, color=color)


def _tokenize(text: str) -> list[str]:
    """Split into tokens keeping spaces attached to the preceding word."""
    if not text:
        return []
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch == " " and buf:
            buf += ch
            # Emit once we hit a non-space or end
            tokens.append(buf)
            buf = ""
        elif ch == " ":
            # Leading spaces: emit as own token
            tokens.append(ch)
        else:
            if buf.endswith(" "):
                tokens.append(buf)
                buf = ""
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


# ── Main apply function ───────────────────────────────────────────────────────

def apply_text_edits(
    doc: fitz.Document,
    orig_doc: fitz.Document,
    page_id_map: dict[str, int],
    page_ops: list[dict[str, Any]],
    text_edits: list[dict[str, Any]],
) -> list[str]:
    """
    Apply confirmed text edits to `doc` (already rebuilt from page_ops).

    1. Redact all original-text lines on the page (batched, once per page).
    2. Re-insert new text using TextWriter.

    Returns a list of non-fatal warning strings.
    """
    warnings: list[str] = []

    # Build sourceIndex lookup
    src_by_pid: dict[str, int] = {
        op["pageId"]: int(op.get("sourceIndex", -1))
        for op in page_ops
        if op.get("pageId")
    }

    # Group edits by pageId
    edits_by_page: dict[str, list[dict[str, Any]]] = {}
    for edit in text_edits:
        pid = edit.get("pageId", "")
        edits_by_page.setdefault(pid, []).append(edit)

    for page_id, page_edits in edits_by_page.items():
        new_idx = page_id_map.get(page_id)
        if new_idx is None:
            continue
        src_idx = src_by_pid.get(page_id, -1)
        if src_idx < 0 or src_idx >= len(orig_doc):
            warnings.append(f"Page {page_id}: source not found, skipping text edits.")
            continue

        new_page = doc[new_idx]
        orig_page = orig_doc[src_idx]

        raw = orig_page.get_text(
            "rawdict",
            flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES,
        )
        span_lookup = _build_span_lookup(raw, page_id)

        redact_rects: list[list[float]] = []
        insertions: list[dict[str, Any]] = []

        for edit in page_edits:
            span_ids: list[str] = edit.get("spanIds", [])
            new_text_runs: list[dict[str, Any]] = edit.get("newText", [])
            overflow_policy: str = edit.get("overflowPolicy", "shrink")

            if not span_ids or not new_text_runs:
                continue

            spans = [span_lookup[sid] for sid in span_ids if sid in span_lookup]
            if not spans:
                warnings.append(f"Page {page_id}: spans {span_ids[:2]} not found.")
                continue

            first_span = spans[0]
            dom_size = float(first_span.get("size", 12))
            font_name = first_span.get("font", "")
            flags = int(first_span.get("flags", 0))
            bold = bool(flags & (1 << 4))
            italic = bool(flags & (1 << 1))
            all_new_text = _extract_all_text(new_text_runs)

            # Font resolution (Tier A / B / C) — raises ValueError on failure
            try:
                font_res = resolve_font(orig_doc, orig_page, font_name, bold, italic, all_new_text)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

            fitz_font = _get_fitz_font(font_res)

            # Edit bounding box (union of all span bboxes)
            all_bboxes = [s.get("bbox", [0, 0, 0, 0]) for s in spans]
            para_x0 = min(b[0] for b in all_bboxes)
            para_y0 = min(b[1] for b in all_bboxes)
            para_x1 = max(b[2] for b in all_bboxes)
            available_width = para_x1 - para_x0

            # First line baseline Y
            first_origin = first_span.get("origin")
            baseline_y = float(first_origin[1]) if first_origin else float(para_y0 + dom_size)

            # Compute scale factor
            s = 1.0
            actual_w = _runs_total_width(new_text_runs, dom_size, fitz_font, 1.0)
            if actual_w > available_width and overflow_policy == "shrink":
                s = _find_shrink_scale(new_text_runs, dom_size, available_width, fitz_font)
                if _runs_total_width(new_text_runs, dom_size, fitz_font, s) > available_width:
                    warnings.append(
                        f"Page {page_id}: text overflows at min scale ({s:.2f}). Overflowing."
                    )

            line_height = (fitz_font.ascender - fitz_font.descender) * dom_size * s

            # Collect line redaction rects
            line_rects = _line_rect_from_span_ids(span_ids, raw)
            redact_rects.extend(line_rects)

            insertions.append({
                "start_x": para_x0,
                "start_y": baseline_y,
                "right_x": para_x1,
                "runs": new_text_runs,
                "dom_size": dom_size,
                "s": s,
                "font_res": font_res,
                "fitz_font": fitz_font,
                "line_height": line_height,
                "overflow_policy": overflow_policy,
            })

        # ── Redact: batch all annotations then apply once per page ────────────
        for rect in redact_rects:
            # Transparent fill preserves vector cell backgrounds and shading.
            # graphics=NONE below leaves those graphics untouched.
            new_page.add_redact_annot(fitz.Rect(rect), fill=False, cross_out=False)
        if redact_rects:
            new_page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            )

        # ── Re-insert ─────────────────────────────────────────────────────────
        for ins in insertions:
            _register_font(new_page, ins["font_res"])
            _write_runs(
                new_page,
                ins["runs"],
                ins["dom_size"],
                ins["s"],
                ins["fitz_font"],
                ins["start_x"],
                ins["start_y"],
                ins["right_x"],
                ins["line_height"],
                ins["overflow_policy"],
            )

    return warnings


# ── Preflight endpoint ────────────────────────────────────────────────────────

@router.post("/api/sejda/preflight-edit")
async def preflight_edit(
    file: UploadFile = File(...),
    source_index: int = Form(...),
    page_id: str = Form(...),
    span_ids_json: str = Form(...),
    runs_json: str = Form(...),
    overflow_policy: str = Form("shrink"),
    available_width: float = Form(...),
    dom_size: float = Form(...),
    font_name: str = Form(""),
    bold: str = Form("false"),
    italic: str = Form("false"),
) -> JSONResponse:
    """
    Check font-resolution tier and overflow for a proposed text edit.
    Returns: { tier, scale_factor, fits, warning }
    """
    raw = await file.read()
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse PDF.")

    if source_index < 0 or source_index >= len(doc):
        doc.close()
        raise HTTPException(status_code=422, detail="source_index out of range.")

    try:
        runs: list[dict[str, Any]] = json.loads(runs_json)
    except json.JSONDecodeError:
        doc.close()
        raise HTTPException(status_code=422, detail="Invalid runs_json.")

    is_bold = bold.lower() in ("1", "true", "yes")
    is_italic = italic.lower() in ("1", "true", "yes")
    page = doc[source_index]
    all_text = _extract_all_text(runs)

    try:
        font_res = resolve_font(doc, page, font_name, is_bold, is_italic, all_text)
    except ValueError as exc:
        doc.close()
        return JSONResponse(content={
            "tier": "error",
            "scale_factor": None,
            "fits": False,
            "warning": str(exc),
        })

    fitz_font = _get_fitz_font(font_res)
    actual_w = _runs_total_width(runs, dom_size, fitz_font, 1.0)
    fits = actual_w <= available_width
    scale_factor = 1.0
    warning = ""

    if not fits:
        if overflow_policy == "shrink":
            scale_factor = _find_shrink_scale(runs, dom_size, available_width, fitz_font)
            if _runs_total_width(runs, dom_size, fitz_font, scale_factor) > available_width:
                warning = (
                    f"Text will overflow even at minimum scale ({scale_factor:.0%}). "
                    "Some content may be cut off."
                )
        elif overflow_policy == "overflow":
            warning = "Text will overflow the original bounding box."
        elif overflow_policy == "truncate":
            warning = "Text will be truncated to fit the original bounding box."

    if not warning and font_res.tier == "C":
        warning = (
            "Using Ubuntu fallback font (OFL) — visual appearance may differ "
            "from the original embedded font."
        )

    doc.close()
    return JSONResponse(content={
        "tier": font_res.tier,
        "scale_factor": round(scale_factor, 4),
        "fits": fits,
        "warning": warning,
    })
