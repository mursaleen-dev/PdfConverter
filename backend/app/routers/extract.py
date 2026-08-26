"""
POST /api/sejda/extract-page  — extract structured text from one PDF page.
POST /api/sejda/search        — text search across pages via page.search_for().

Extraction schema mirrors frontend types ExtractedSpan / ExtractedParagraph /
ExtractedPage.  SpanIds use the stable scheme "{pageId}:{block}:{line}:{span}".

Grouping heuristics:

  COLUMN GUARD (horizontal — Fix 1):
    A page-level MEDIAN word-gap is computed from inter-span gaps ≤ _WORD_GAP_CUTOFF_PT
    (5 pt by default), so column separations can never inflate the modal estimate.
    Falls back to _WORD_GAP_FLOOR_PT (2 pt) when no qualifying gaps exist — common
    on data-only pages whose cells contain no multi-word text.
    A gap that exceeds  GAP_BREAK = max(_COL_GAP_RATIO × modal, _COL_GAP_PAGE_FRAC × w)
    is treated as a column boundary.  The page-width floor catches tight layouts where
    the modal estimate cannot distinguish word-gaps from small column gaps.

  BLOCK BOUNDARY (Fix 2):
    PyMuPDF block indices are respected as hard paragraph boundaries.  Each block is
    processed independently; paragraphs never span blocks.

  ROW / PROSE GUARD (vertical — Fix 3):
    Each raw_line is tagged with src_line_idx (which PyMuPDF line it came from) and
    left_x (left-edge x-coordinate).  Two consecutive raw_lines are merged only when
    ALL of the following hold (prose-continuation test):
      (a) different src_line_idx  — same-row column fragments always split
      (b) left-x within _LEFT_X_TOL_PT  — same left-margin → wrapped prose
      (c) vertical gap ≤ _LEADING_BREAK_RATIO × modal block leading
      (d) no font-size jump > _SIZE_BREAK_RATIO
    Rows in different columns (different left-x) and column fragments from the same
    source line (same src_line_idx) both start new paragraphs.

  DEBUG:
    Set DEBUG_GROUPING = True (below) to have the backend log every paragraph's
    spanIds together with the inter-span gaps in points and the page thresholds.
    Restart uvicorn after toggling; output appears in the server console.
"""
from __future__ import annotations

import json
import logging
import statistics
import unicodedata
import base64
import re
from collections import Counter
from typing import Any

import fitz
from app.text_span_utils import infer_font_style, split_mixed_direction_span
from app.type3_fonts import type3_face_style
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)
_MAX_EMBEDDED_FONT_BYTES = 4 * 1024 * 1024


def _extract_browser_fonts(page: fitz.Page) -> dict[str, str]:
    """Expose page fonts to the inline editor for an exact visual preview."""
    fonts: dict[str, str] = {}
    total = 0
    for entry in page.get_fonts(full=True):
        xref, basefont = int(entry[0]), str(entry[3])
        if xref <= 0:
            continue
        family = re.sub(r"^[A-Z]{6}\+", "", basefont)
        if family in fonts:
            continue
        try:
            _name, ext, _font_type, data = page.parent.extract_font(xref)
        except Exception:
            continue
        if not data or total + len(data) > _MAX_EMBEDDED_FONT_BYTES:
            continue
        mime = "font/otf" if str(ext).lower() in {"otf", "cff"} else "font/ttf"
        fonts[family] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        total += len(data)
    return fonts


MAX_FILE_MB = 50

# ── Dev toggle ────────────────────────────────────────────────────────────────

# Set True → backend logs span IDs, inter-span gaps, and thresholds per page.
# Keep False in production.
DEBUG_GROUPING: bool = False

# ── Grouping constants ────────────────────────────────────────────────────────

# Column guard (Fix 1) — horizontal split within a PyMuPDF line
_WORD_GAP_CUTOFF_PT  = 5.0   # gaps ≤ this are candidates for the page word-gap median;
                               # larger gaps are column separators and must not inflate it
_WORD_GAP_FLOOR_PT   = 2.0   # fallback median when no qualifying gaps exist (data-only pages)
_COL_GAP_RATIO       = 2.5   # split when gap > N × page-median-word-gap
_COL_GAP_PAGE_FRAC   = 0.03  # split when gap > N × page width (floor for tight layouts)

# Row guard (Fix 3) — vertical grouping between raw_lines
_LEADING_BREAK_RATIO = 1.5   # vertical gap > N × modal block leading → new paragraph
_SIZE_BREAK_RATIO    = 1.05  # font-size ratio > N between lines → new paragraph
                               # 5% tolerance: catches label(8pt)/value(10pt) pairs (ratio 1.25)
                               # while tolerating negligible rendering deltas in uniform prose
_LEFT_X_TOL_PT       = 1.5   # left-x must be within N pt to be considered prose wrapping


# ── Colour helper ─────────────────────────────────────────────────────────────

def _color_to_hex(color_int: int) -> str:
    """PyMuPDF packed sRGB int → '#rrggbb'."""
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Grouping helpers ──────────────────────────────────────────────────────────

def _page_word_gap(text_blocks: list[dict[str, Any]], page_w: float) -> float:
    """
    Page-level MEDIAN intra-word spacing.

    Only inter-span gaps ≤ _WORD_GAP_CUTOFF_PT are considered; this excludes
    column separators (which are larger) from inflating the estimate.
    Falls back to _WORD_GAP_FLOOR_PT when the page has no qualifying gaps
    (e.g. ticket/table pages whose cells are all single tokens).
    """
    gaps: list[float] = []
    for block in text_blocks:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            for i in range(1, len(spans)):
                g = float(spans[i]["bbox"][0]) - float(spans[i - 1]["bbox"][2])
                if 0 < g <= _WORD_GAP_CUTOFF_PT:
                    gaps.append(g)
    if not gaps:
        return _WORD_GAP_FLOOR_PT
    return statistics.median(gaps)


def _col_gap_threshold(page_median_wg: float, page_w: float) -> float:
    """
    Minimum gap that constitutes a column boundary.

    = max(2.5 × page-median-word-gap,  3% × page-width)

    The page-width floor catches tight layouts where even the corrected median
    cannot be reliably estimated (returns _WORD_GAP_FLOOR_PT = 2 pt).
    In that case the threshold is 3% × page-width (≈ 17.9 pt for A4).
    """
    return max(_COL_GAP_RATIO * page_median_wg, page_w * _COL_GAP_PAGE_FRAC)


def _split_line_at_column_gaps(
    spans: list[dict[str, Any]],
    col_threshold: float,
) -> list[list[dict[str, Any]]]:
    """
    Split a list of spans into sub-lists wherever the horizontal gap between
    consecutive spans exceeds col_threshold.
    Returns one or more span-groups, each representing a distinct column fragment.
    """
    if not spans:
        return []
    # Content-stream order is not reliably visual order, especially for mixed
    # Arabic/Latin rows. Geometry must drive cell separation.
    ordered = sorted(spans, key=lambda span: float(span["bbox"][0]))
    groups: list[list[dict[str, Any]]] = [[ordered[0]]]
    for span in ordered[1:]:
        gap = span["bbox"][0] - groups[-1][-1]["bbox"][2]
        if gap > col_threshold:
            groups.append([span])
        else:
            groups[-1].append(span)
    return groups


def _coalesce_selection_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine font-fragmented pieces of one value into one selectable unit."""
    if len(spans) < 2:
        return spans

    ordered = sorted(spans, key=lambda span: float(span["bbox"][0]))
    groups: list[list[dict[str, Any]]] = [[ordered[0]]]
    for span in ordered[1:]:
        previous = groups[-1][-1]
        gap = float(span["bbox"][0]) - float(previous["bbox"][2])
        size = min(float(span["size"]), float(previous["size"]))
        same_style = (
            span["isLtr"] == previous["isLtr"]
            and span.get("script") == previous.get("script")
            and span["bold"] == previous["bold"]
            and span["italic"] == previous["italic"]
            and abs(float(span["baselineY"]) - float(previous["baselineY"])) <= 2.5
        )
        if same_style and gap <= max(3.0, size * 0.65):
            groups[-1].append(span)
        else:
            groups.append([span])

    merged: list[dict[str, Any]] = []
    for group in groups:
        if len(group) == 1:
            item = group[0]
            item["memberSpanIds"] = [item["spanId"]]
            merged.append(item)
            continue

        reading_order = group if group[0]["isLtr"] else list(reversed(group))
        item = dict(reading_order[0])
        boxes = [part["bbox"] for part in group]
        text_parts = [reading_order[0]["text"]]
        for previous, current in zip(reading_order, reading_order[1:]):
            visual_gap = (
                float(current["bbox"][0]) - float(previous["bbox"][2])
                if item["isLtr"]
                else float(previous["bbox"][0]) - float(current["bbox"][2])
            )
            needs_space = (
                visual_gap > min(float(previous["size"]), float(current["size"])) * 0.15
                and not text_parts[-1].endswith((" ", "\n"))
                and not current["text"].startswith((" ", "\n"))
            )
            text_parts.append((" " if needs_space else "") + current["text"])
        item["text"] = "".join(text_parts)
        item["bbox"] = [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ]
        item["spanId"] = reading_order[0]["spanId"]
        item["memberSpanIds"] = [
            span_id
            for part in reading_order
            for span_id in part.get("memberSpanIds", [part["spanId"]])
        ]
        merged.append(item)
    return merged


def _sample_background_color(
    pix: fitz.Pixmap,
    bbox: list[float],
    page_w: float,
    page_h: float,
) -> str:
    """Estimate the local fill around text without sampling its glyph pixels."""
    x0, y0, x1, y1 = bbox
    left = min(max(int(x0) - 3, 0), max(int(page_w) - 1, 0))
    right = min(max(int(x1) + 3, left), max(int(page_w) - 1, 0))
    top = min(max(int(y0), 0), max(int(page_h) - 1, 0))
    bottom = min(max(int(y1), top), max(int(page_h) - 1, 0))
    area = max(1, (right - left + 1) * (bottom - top + 1))
    step = max(1, round((area / 20_000) ** 0.5))
    samples = [
        tuple(pix.pixel(x, y)[:3])
        for y in range(top, bottom + 1, step)
        for x in range(left, right + 1, step)
    ]
    if not samples:
        return "#ffffff"
    # The dominant color inside the text line is its cell/background fill.
    # Glyphs and borders occupy fewer pixels and become minority colors.
    quantized = [
        tuple(min(255, round(channel / 8) * 8) for channel in sample)
        for sample in samples
    ]
    rgb = Counter(quantized).most_common(1)[0][0]
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _modal_line_gap(line_bboxes: list[list[float]]) -> float:
    """Modal vertical gap between consecutive lines (positive gaps only)."""
    gaps = []
    for i in range(1, len(line_bboxes)):
        g = line_bboxes[i][1] - line_bboxes[i - 1][3]
        if g > 0:
            gaps.append(round(g, 1))
    if not gaps:
        return float("inf")
    return Counter(gaps).most_common(1)[0][0]


def _dominant_size(line_spans: list[dict[str, Any]]) -> float:
    """Font size of the span with the most characters on this line."""
    best_size = 12.0
    best_len = 0
    for s in line_spans:
        tl = len(s.get("text", ""))
        if tl > best_len:
            best_len = tl
            best_size = float(s.get("size", 12))
    return best_size


def _dominant_style(line_spans: list[dict[str, Any]]) -> tuple[bool, bool]:
    """(bold, italic) of the span with the most characters on this line."""
    best_bold = False
    best_italic = False
    best_len = 0
    for s in line_spans:
        tl = len(s.get("text", ""))
        if tl > best_len:
            best_len = tl
            best_bold = bool(s.get("bold", False))
            best_italic = bool(s.get("italic", False))
    return best_bold, best_italic


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_page_data(
    page: fitz.Page,
    page_id: str,
    source_index: int,
) -> dict[str, Any]:
    """Extract structured text from `page` into our JSON schema."""
    w = page.rect.width
    h = page.rect.height

    raw = page.get_text(
        "rawdict",
        flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES,
    )
    text_blocks = [b for b in raw.get("blocks", []) if b.get("type") == 0]
    scanned = len(text_blocks) == 0
    page_pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB, alpha=False)

    # Fix 1: page-level word-gap median and derived column threshold (once per page)
    pg_median_wg = _page_word_gap(text_blocks, w)
    col_threshold = _col_gap_threshold(pg_median_wg, w)

    if DEBUG_GROUPING:
        logger.debug(
            "PAGE %s | w=%.0fpt | median_word_gap=%.2fpt | col_threshold=%.2fpt",
            page_id, w, pg_median_wg, col_threshold,
        )

    paragraphs: list[dict[str, Any]] = []
    para_counter = 0

    for block in text_blocks:
        # Fix 2: each PyMuPDF block is a hard paragraph boundary
        block_num = block.get("number", para_counter)

        # ── First pass: build raw_lines, applying column split per PyMuPDF line ──
        raw_lines: list[dict[str, Any]] = []

        for line_idx, line in enumerate(block.get("lines", [])):
            dir_vec = list(line.get("dir", [1.0, 0.0]))

            raw_spans: list[dict[str, Any]] = []
            for span_idx, span in enumerate(line.get("spans", [])):
                segments = split_mixed_direction_span(span)
                for segment_idx, segment, direction in segments:
                    chars = segment.get("chars", [])
                    # Convert presentation forms and compatibility ligatures to
                    # normal Unicode so browsers can shape every script correctly.
                    span_text = unicodedata.normalize(
                        "NFKC", "".join(c.get("c", "") for c in chars)
                    )
                    if not span_text.strip():
                        continue

                    flags = int(segment.get("flags", 0))
                    size = float(segment.get("size", 12))
                    color_int = int(segment.get("color", 0))
                    font_name = segment.get("font", "")
                    bold, italic = infer_font_style(font_name, flags)
                    type3_style = type3_face_style(page.parent, font_name, page)
                    if type3_style is not None:
                        bold = type3_style.weight >= 600
                        italic = type3_style.italic
                    sbbox = list(segment.get("bbox", [0, 0, 0, 0]))
                    origin = list(segment.get("origin", [sbbox[0], sbbox[3]]))
                    asc_raw = float(segment.get("ascender", 0.83))
                    desc_raw = float(segment.get("descender", -0.21))
                    base_id = f"{page_id}:{block_num}:{line_idx}:{span_idx}"
                    span_id = base_id if len(segments) == 1 else f"{base_id}~{segment_idx}"

                    raw_spans.append({
                        "spanId":      span_id,
                        "text":        span_text,
                        "bbox":        [round(v, 2) for v in sbbox],
                        "size":        round(size, 2),
                        "bold":        bold,
                        "italic":      italic,
                        "color":       _color_to_hex(color_int),
                        "backgroundColor": _sample_background_color(
                            page_pix, sbbox, w, h
                        ),
                        "fontName":    font_name,
                        "script":      segment.get("_editScript", "UNKNOWN"),
                        "dir":         [1.0, 0.0] if direction == "ltr" else [-1.0, 0.0],
                        "isLtr":       direction == "ltr",
                        "baselineY":   round(float(origin[1]), 2),
                        "ascenderPt":  round(abs(asc_raw) * size, 2),
                        "descenderPt": round(abs(desc_raw) * size, 2),
                    })

            if not raw_spans:
                continue

            # Fix 1: column guard — split at gaps that exceed col_threshold
            if DEBUG_GROUPING and len(raw_spans) > 1:
                gap_report = " | ".join(
                    f"gap({raw_spans[i]['text'][:8]!r}→{raw_spans[i+1]['text'][:8]!r})="
                    f"{raw_spans[i+1]['bbox'][0] - raw_spans[i]['bbox'][2]:.1f}pt"
                    for i in range(len(raw_spans) - 1)
                )
                logger.debug(
                    "  block=%d line=%d  threshold=%.1fpt  %s",
                    block_num, line_idx, col_threshold, gap_report,
                )

            col_groups = _split_line_at_column_gaps(raw_spans, col_threshold)

            for col_spans in col_groups:
                col_spans = _coalesce_selection_spans(col_spans)
                if not col_spans:
                    continue
                bboxes = [s["bbox"] for s in col_spans]
                group_bbox = [
                    min(b[0] for b in bboxes),
                    min(b[1] for b in bboxes),
                    max(b[2] for b in bboxes),
                    max(b[3] for b in bboxes),
                ]
                avg_baseline = sum(s["baselineY"] for s in col_spans) / len(col_spans)
                raw_lines.append({
                    "spans":        col_spans,
                    "bbox":         [round(v, 2) for v in group_bbox],
                    "baselineY":    round(avg_baseline, 2),
                    "src_line_idx": line_idx,      # Fix 3a: same-row guard
                    "left_x":       round(group_bbox[0], 2),  # Fix 3b: prose-wrap guard
                })

        if not raw_lines:
            continue

        # ── Second pass: group raw_lines into paragraphs (Fix 3) ─────────────────
        #
        # Merge only when all prose-continuation conditions hold:
        #   (a) different src_line_idx  → same-row column fragments always split
        #   (b) left-x within _LEFT_X_TOL_PT  → prose wrapping keeps same left margin
        #   (c) gap ≤ 1.5 × modal block leading
        #   (d) no font-size jump > 5%
        #   (e) no bold/italic style change (catches section boundaries in letters)
        #
        # Same-src-line, left-x shift, large gap, size break, or style break all
        # start a new paragraph.  PyMuPDF's block boundaries are the hard outer
        # fence — blocks are already processed independently.

        line_bboxes = [ln["bbox"] for ln in raw_lines]
        modal_lg = _modal_line_gap(line_bboxes)

        para_runs: list[list[dict[str, Any]]] = [[raw_lines[0]]]
        prev_size = _dominant_size(raw_lines[0]["spans"])
        prev_bold, prev_italic = _dominant_style(raw_lines[0]["spans"])

        for i in range(1, len(raw_lines)):
            prev_line = raw_lines[i - 1]
            curr_line = raw_lines[i]

            gap       = curr_line["bbox"][1] - prev_line["bbox"][3]
            curr_size = _dominant_size(curr_line["spans"])
            curr_bold, curr_italic = _dominant_style(curr_line["spans"])

            # (a) Hard rule: column fragments from the same PyMuPDF line are
            #     separate units — they share a baseline (gap ≤ 0).
            same_src = curr_line["src_line_idx"] == prev_line["src_line_idx"]

            # (b) Left-margin shift: wrapped prose keeps the same left-x.
            #     Table cells in different rows/columns shift left-x.
            left_shift = abs(curr_line["left_x"] - prev_line["left_x"]) > _LEFT_X_TOL_PT

            # (c) Leading break: gap significantly larger than the block's modal
            #     line-gap signals extra inter-paragraph spacing.
            leading_break = (
                modal_lg < float("inf")
                and gap > _LEADING_BREAK_RATIO * modal_lg
            )

            # (d) Size break
            size_break = (
                curr_size > 0 and prev_size > 0
                and (curr_size / prev_size > _SIZE_BREAK_RATIO
                     or prev_size / curr_size > _SIZE_BREAK_RATIO)
            )

            # (e) Style break: bold or italic changes between consecutive lines
            #     (e.g. regular address → bold subject heading in a letter).
            style_break = (curr_bold != prev_bold) or (curr_italic != prev_italic)

            prose_cont = not same_src and not left_shift and not leading_break and not size_break and not style_break

            if prose_cont:
                para_runs[-1].append(curr_line)
            else:
                para_runs.append([curr_line])

            prev_size = curr_size
            prev_bold, prev_italic = curr_bold, curr_italic

        for run in para_runs:
            if not run:
                continue
            all_span_ids = [
                span_id
                for ln in run
                for span in ln["spans"]
                for span_id in span.get("memberSpanIds", [span["spanId"]])
            ]
            all_bboxes   = [ln["bbox"] for ln in run]
            para_bbox = [
                min(b[0] for b in all_bboxes),
                min(b[1] for b in all_bboxes),
                max(b[2] for b in all_bboxes),
                max(b[3] for b in all_bboxes),
            ]
            para = {
                "paraId":  f"{page_id}:para:{para_counter}",
                "lines":   run,
                "bbox":    [round(v, 2) for v in para_bbox],
                "spanIds": all_span_ids,
            }
            paragraphs.append(para)

            if DEBUG_GROUPING:
                logger.debug(
                    "  → para %s: %d spans | bbox=[%.0f,%.0f,%.0f,%.0f]",
                    para["paraId"], len(all_span_ids), *para_bbox,
                )
                for ln in run:
                    for j, span in enumerate(ln["spans"]):
                        nxt = ln["spans"][j + 1] if j + 1 < len(ln["spans"]) else None
                        gap_to_next = (
                            f"  gap→next={nxt['bbox'][0] - span['bbox'][2]:.1f}pt"
                            if nxt else ""
                        )
                        logger.debug(
                            "      spanId=%s  text=%r  bbox=[%.0f,%.0f,%.0f,%.0f]%s",
                            span["spanId"], span["text"][:20],
                            *span["bbox"], gap_to_next,
                        )

            para_counter += 1

    return {
        "pageId":      page_id,
        "sourceIndex": source_index,
        "width":       round(w, 2),
        "height":      round(h, 2),
        "scanned":     scanned,
        "fonts":       _extract_browser_fonts(page),
        "paragraphs":  paragraphs,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/sejda/extract-page")
async def extract_page(
    file: UploadFile = File(...),
    page_id: str = Form(...),
    source_index: int = Form(...),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_MB} MB.")
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse PDF.")

    if source_index < 0 or source_index >= len(doc):
        doc.close()
        raise HTTPException(status_code=422, detail="source_index out of range.")

    page = doc[source_index]
    result = extract_page_data(page, page_id, source_index)
    doc.close()
    return JSONResponse(content=result)


@router.post("/api/sejda/search")
async def search_text(
    file: UploadFile = File(...),
    query: str = Form(...),
    page_scope_json: str | None = Form(None),
) -> JSONResponse:
    """
    Search for `query` across pages.

    page_scope_json: optional JSON array of {"sourceIndex": int, "pageId": str}.
    Returns {"matches": [{pageSourceIndex, pageId, bbox, matchText}]}.
    """
    if not query or len(query) > 500:
        raise HTTPException(status_code=422, detail="Query must be 1–500 characters.")

    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_MB} MB.")

    page_scope: list[dict[str, Any]] | None = None
    if page_scope_json:
        try:
            page_scope = json.loads(page_scope_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid page_scope_json.")

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse PDF.")

    pages_to_search: list[tuple[int, str]] = []
    if page_scope:
        for entry in page_scope:
            pages_to_search.append((int(entry["sourceIndex"]), str(entry["pageId"])))
    else:
        for i in range(len(doc)):
            pages_to_search.append((i, str(i)))

    matches: list[dict[str, Any]] = []
    for src_idx, pg_id in pages_to_search:
        if src_idx < 0 or src_idx >= len(doc):
            continue
        page = doc[src_idx]
        rects = page.search_for(query, quads=False)
        for rect in rects:
            matches.append({
                "pageSourceIndex": src_idx,
                "pageId": pg_id,
                "bbox": [round(rect.x0, 2), round(rect.y0, 2),
                         round(rect.x1, 2), round(rect.y1, 2)],
                "matchText": query,
            })

    doc.close()
    return JSONResponse(content={"matches": matches})
