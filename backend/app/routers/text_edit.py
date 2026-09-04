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
import unicodedata
from collections import Counter
from typing import Any

import fitz
import pymupdf_fonts
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.font_resolver import FontResolution, resolve_font, source_face_style
from app.text_span_utils import split_mixed_direction_span
from app.type3_fonts import (
    encode_with_type3,
    restore_type3_resources,
    snapshot_type3_resources,
    type3_face_style,
    write_type3_text,
)

router = APIRouter()

MAX_FILE_MB = 50
SHRINK_MIN_S = 0.70
SHRINK_STEP = 0.02
SHRINK_MIN_SIZE_PT = 6.0


# ── Font registration cache ───────────────────────────────────────────────────

def _register_font(page: fitz.Page, res: FontResolution | None) -> None:
    """Register a font with the page (safe to call multiple times)."""
    if not res or not res.fontbuffer:
        return
    try:
        page.insert_font(fontname=res.fontname, fontbuffer=res.fontbuffer)
    except Exception:
        pass  # already registered


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


def _is_rtl_text(text: str) -> bool:
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi in {"R", "AL", "AN"}:
            return True
        if bidi in {"L", "EN"}:
            return False
    return False


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
                segments = split_mixed_direction_span(span)
                base_id = f"{page_id}:{block_num}:{line_idx}:{span_idx}"
                for segment_idx, segment, _direction in segments:
                    span_id = base_id if len(segments) == 1 else f"{base_id}~{segment_idx}"
                    lookup[span_id] = segment
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
    selected: dict[tuple[int, int], set[str]] = {}
    for sid in span_ids:
        parts = sid.rsplit(":", 3)
        if len(parts) == 4:
            try:
                key = (int(parts[1]), int(parts[2]))
                selected.setdefault(key, set()).add(parts[3])
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
            line_spans: list[dict[str, Any]] = []
            for span_idx, span in enumerate(line.get("spans", [])):
                segments = split_mixed_direction_span(span)
                for segment_idx, segment, _direction in segments:
                    token = str(span_idx) if len(segments) == 1 else f"{span_idx}~{segment_idx}"
                    if token in selected_indices:
                        line_spans.append(segment)
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


def _fill_rgb(fill: Any) -> tuple[float, float, float] | None:
    if not fill:
        return None
    try:
        red, green, blue = float(fill[0]), float(fill[1]), float(fill[2])
    except (TypeError, ValueError, IndexError):
        return None
    if max(red, green, blue) > 1.0:
        red, green, blue = red / 255.0, green / 255.0, blue / 255.0
    return (
        max(0.0, min(1.0, red)),
        max(0.0, min(1.0, green)),
        max(0.0, min(1.0, blue)),
    )


def _point_in_rect(x: float, y: float, rect: fitz.Rect, pad: float = 0.5) -> bool:
    return rect.x0 - pad <= x <= rect.x1 + pad and rect.y0 - pad <= y <= rect.y1 + pad


def _vector_fill_behind(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float] | None:
    """Smallest filled drawing under the text — heading bars and table cells."""
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    page_area = float(page.rect.width * page.rect.height) or 1.0
    matches: list[tuple[float, tuple[float, float, float]]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    for drawing in drawings:
        rgb = _fill_rgb(drawing.get("fill"))
        if rgb is None:
            continue
        opacity = drawing.get("fill_opacity")
        if opacity is not None and float(opacity) <= 0.01:
            continue
        found_item = False
        for item in drawing.get("items") or []:
            if not item or item[0] != "re" or len(item) < 2:
                continue
            try:
                item_rect = fitz.Rect(item[1])
            except Exception:
                continue
            area = float(item_rect.width * item_rect.height)
            if area <= 8 or area > page_area * 0.5:
                continue
            if _point_in_rect(cx, cy, item_rect):
                matches.append((area, rgb))
                found_item = True
        if found_item:
            continue
        try:
            draw_rect = fitz.Rect(drawing.get("rect"))
        except Exception:
            continue
        area = float(draw_rect.width * draw_rect.height)
        if draw_rect.width < 8 or draw_rect.height < 4 or area > page_area * 0.5:
            continue
        if _point_in_rect(cx, cy, draw_rect):
            matches.append((area, rgb))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _dominant_clip_rgb(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """Mode of pixels inside the text box — never the page above a heading bar."""
    pad_x = min(1.5, max(0.0, rect.width * 0.08))
    pad_y = min(1.5, max(0.0, rect.height * 0.15))
    inset = fitz.Rect(rect.x0 + pad_x, rect.y0 + pad_y, rect.x1 - pad_x, rect.y1 - pad_y)
    if inset.is_empty or inset.width < 1 or inset.height < 1:
        inset = fitz.Rect(rect)
    try:
        pix = page.get_pixmap(
            matrix=fitz.Matrix(2, 2),
            clip=inset,
            colorspace=fitz.csRGB,
            alpha=False,
        )
    except Exception:
        return (1.0, 1.0, 1.0)
    if pix.n < 3 or pix.width <= 0 or pix.height <= 0:
        return (1.0, 1.0, 1.0)
    step = max(1, min(pix.width, pix.height) // 12)
    samples = [
        tuple(pix.pixel(x, y)[:3])
        for y in range(0, pix.height, step)
        for x in range(0, pix.width, step)
    ]
    if not samples:
        return (1.0, 1.0, 1.0)
    quantized = [
        tuple(min(255, round(channel / 8) * 8) for channel in sample)
        for sample in samples
    ]
    red, green, blue = Counter(quantized).most_common(1)[0][0]
    return (red / 255.0, green / 255.0, blue / 255.0)


def _sample_bg_rgb(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """Local fill behind text: vector cell/heading first, then pixels inside the box."""
    vector = _vector_fill_behind(page, rect)
    if vector is not None:
        return vector
    return _dominant_clip_rgb(page, rect)


def _point_xy(value: Any) -> tuple[float, float] | None:
    try:
        return (float(value.x), float(value.y))
    except Exception:
        pass
    try:
        return (float(value[0]), float(value[1]))
    except Exception:
        return None


_TABLE_INSET_PT = 0.8


def _thin_horizontal_strokes(page: fitz.Page) -> list[tuple[float, float, float]]:
    """Return (x0, x1, y) for table rules: hairlines and cell rectangle edges."""
    strokes: list[tuple[float, float, float]] = []
    page_area = float(page.rect.width * page.rect.height) or 1.0
    try:
        drawings = page.get_drawings()
    except Exception:
        return strokes
    for drawing in drawings:
        if float(drawing.get("width") or 0) > 1.5:
            continue
        for item in drawing.get("items", []):
            if not item:
                continue
            kind = item[0]
            if kind == "l" and len(item) >= 3:
                start, end = _point_xy(item[1]), _point_xy(item[2])
                if start is None or end is None:
                    continue
                if abs(start[1] - end[1]) > 0.75:
                    continue
                y = (start[1] + end[1]) / 2
                x0, x1 = min(start[0], end[0]), max(start[0], end[0])
            elif kind == "re" and len(item) >= 2:
                try:
                    rect = fitz.Rect(item[1])
                except Exception:
                    continue
                if rect.width < 1.0:
                    continue
                if rect.width * rect.height > page_area * 0.45:
                    continue
                if rect.height <= 1.5:
                    y = (rect.y0 + rect.y1) / 2
                    x0, x1 = float(rect.x0), float(rect.x1)
                    if x1 - x0 >= 1.0:
                        strokes.append((x0, x1, y))
                    continue
                # Full table cells: the stroked/filled rectangle *is* the grid.
                # Record both horizontal edges so paint cannot cover them.
                x0, x1 = float(rect.x0), float(rect.x1)
                strokes.append((x0, x1, float(rect.y0)))
                strokes.append((x0, x1, float(rect.y1)))
                continue
            else:
                continue
            if x1 - x0 < 1.0:
                continue
            strokes.append((x0, x1, y))
    return strokes


def _containing_cell_rect(
    page: fitz.Page,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> fitz.Rect | None:
    """Smallest drawing rectangle that fully contains the text box (a table cell)."""
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    page_area = float(page.rect.width * page.rect.height) or 1.0
    candidates: list[fitz.Rect] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    for drawing in drawings:
        for item in drawing.get("items", []):
            if not item or item[0] != "re" or len(item) < 2:
                continue
            try:
                rect = fitz.Rect(item[1])
            except Exception:
                continue
            if rect.width < 8 or rect.height < 6:
                continue
            if rect.width * rect.height > page_area * 0.45:
                continue
            if rect.x0 - 1 <= center_x <= rect.x1 + 1 and rect.y0 - 1 <= center_y <= rect.y1 + 1:
                candidates.append(rect)
    if not candidates:
        return None
    return min(candidates, key=lambda rect: rect.width * max(rect.height, 1))


def _clamp_rect_above_rules(
    rect: list[float],
    strokes: list[tuple[float, float, float]],
) -> list[float]:
    """Keep redaction/paint from eating a table rule sitting under or above the text."""
    x0, y0, x1, y1 = rect
    mid = (y0 + y1) / 2
    top_limit = y0
    bot_limit = y1
    for sx0, sx1, y in strokes:
        if y < y0 - 2 or y > y1 + 2:
            continue
        if sx1 < x0 - 1 or sx0 > x1 + 1:
            continue
        if y >= mid:
            bot_limit = min(bot_limit, y - 0.7)
        else:
            top_limit = max(top_limit, y + 0.7)
    if bot_limit < top_limit + 0.5:
        bot_limit = top_limit + 0.5
    return [x0, top_limit, x1, bot_limit]


def _clamp_paint_rect(
    rect: list[float],
    page: fitz.Page,
    strokes: list[tuple[float, float, float]],
) -> list[float]:
    """Inset to the table cell, then keep off detected row/column rules."""
    x0, y0, x1, y1 = rect
    cell = _containing_cell_rect(page, x0, y0, x1, y1)
    if cell is not None:
        x0 = max(x0, float(cell.x0) + _TABLE_INSET_PT)
        y0 = max(y0, float(cell.y0) + _TABLE_INSET_PT)
        x1 = min(x1, float(cell.x1) - _TABLE_INSET_PT)
        y1 = min(y1, float(cell.y1) - _TABLE_INSET_PT)
        if x1 < x0 + 0.5:
            x1 = x0 + 0.5
        if y1 < y0 + 0.5:
            y1 = y0 + 0.5
    return _clamp_rect_above_rules([x0, y0, x1, y1], strokes)


def _writable_horizontal_bounds(
    page: fitz.Page,
    span_lookup: dict[str, dict[str, Any]],
    selected_spans: list[dict[str, Any]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    right_to_left: bool,
) -> tuple[float, float]:
    """Expand into unused table-cell space without crossing text or borders."""
    center_y = (y0 + y1) / 2
    cell_left, cell_right = 0.0, float(page.rect.width)
    containing_rects: list[fitz.Rect] = []
    vertical_lines: list[float] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "re":
                rect = fitz.Rect(item[1])
                if (
                    rect.x0 <= x0 <= x1 <= rect.x1
                    and rect.y0 - 1 <= center_y <= rect.y1 + 1
                    and rect.width > 0
                ):
                    containing_rects.append(rect)
            elif item[0] == "l":
                start, end = item[1], item[2]
                if abs(start.x - end.x) <= 0.5 and min(start.y, end.y) - 1 <= center_y <= max(start.y, end.y) + 1:
                    vertical_lines.append(float(start.x))

    if containing_rects:
        cell = min(containing_rects, key=lambda rect: rect.width * max(rect.height, 1))
        cell_left, cell_right = float(cell.x0), float(cell.x1)
    else:
        left_lines = [value for value in vertical_lines if value <= x0]
        right_lines = [value for value in vertical_lines if value >= x1]
        if left_lines:
            cell_left = max(left_lines)
        if right_lines:
            cell_right = min(right_lines)

    selected_objects = {id(span) for span in selected_spans}
    neighbors = [
        span
        for span in span_lookup.values()
        if id(span) not in selected_objects
        and float(span.get("bbox", [0, 0, 0, 0])[3]) > y0
        and float(span.get("bbox", [0, 0, 0, 0])[1]) < y1
    ]
    padding = 1.0
    if right_to_left:
        left_neighbors = [
            float(span["bbox"][2])
            for span in neighbors
            if float(span["bbox"][2]) <= x0
        ]
        writable_left = max(cell_left + padding, max(left_neighbors, default=cell_left) + padding)
        return min(writable_left, x0), x1

    right_neighbors = [
        float(span["bbox"][0])
        for span in neighbors
        if float(span["bbox"][0]) >= x1
    ]
    writable_right = min(cell_right - padding, min(right_neighbors, default=cell_right) - padding)
    return x0, max(writable_right, x1)


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
    right_to_left: bool,
    single_line: bool,
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

    x = right_x if right_to_left else start_x
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
            if right_to_left:
                next_x = x - token_w
                if not single_line and next_x < start_x - 0.5 and x < right_x:
                    x = right_x
                    y += line_height
                    next_x = x - token_w
                if next_x < start_x - 0.5 and overflow_policy == "truncate":
                    continue
                if color not in writers:
                    writers[color] = fitz.TextWriter(page.rect)
                writers[color].append(
                    fitz.Point(next_x, y),
                    token,
                    font=font,
                    fontsize=fs,
                    right_to_left=1,
                )
                x = next_x
                continue

            # Soft-wrap: if adding this token would overflow and we're not at line start
            if not single_line and x + token_w > right_x + 0.5 and x > start_x:
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


def _visually_aligned_baseline(
    runs: list[dict[str, Any]],
    dom_size: float,
    scale: float,
    font: fitz.Font,
    available_width: float,
    line_height: float,
    overflow_policy: str,
    right_to_left: bool,
    source_y0: float,
    source_y1: float,
    fallback_baseline: float,
) -> float:
    """Measure replacement glyphs and center them in the source text box."""
    probe_doc = fitz.open()
    try:
        probe_page = probe_doc.new_page(width=max(1000, available_width + 200), height=500)
        probe_baseline = 250.0
        _write_runs(
            probe_page,
            runs,
            dom_size,
            scale,
            font,
            100.0,
            probe_baseline,
            100.0 + available_width,
            line_height,
            overflow_policy,
            right_to_left,
            True,
        )
        boxes = [
            span["bbox"]
            for block in probe_page.get_text("dict").get("blocks", [])
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if span.get("text")
        ]
        if not boxes:
            return fallback_baseline
        measured_center = (min(box[1] for box in boxes) + max(box[3] for box in boxes)) / 2
        source_center = (source_y0 + source_y1) / 2
        return source_center - (measured_center - probe_baseline)
    finally:
        probe_doc.close()


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

            if not span_ids:
                continue

            spans = [span_lookup[sid] for sid in span_ids if sid in span_lookup]
            if not spans:
                warnings.append(f"Page {page_id}: spans {span_ids[:2]} not found.")
                continue

            # An empty run list is an explicit content deletion: redact the
            # selected spans and preserve surrounding graphics/background.
            if not new_text_runs:
                redact_rects.extend(_line_rect_from_span_ids(span_ids, raw))
                continue

            first_span = spans[0]
            dom_size = float(first_span.get("size", 12))
            font_name = first_span.get("font", "")
            flags = int(first_span.get("flags", 0))
            face = source_face_style(orig_doc, orig_page, font_name, flags)
            bold, italic = face.bold, face.italic
            type3_style = type3_face_style(orig_doc, font_name, orig_page)
            all_new_text = _extract_all_text(new_text_runs)
            right_to_left = _is_rtl_text(all_new_text)

            type3_runs: list[tuple[dict[str, Any], Any]] | None = None
            if not right_to_left:
                encoded: list[tuple[dict[str, Any], Any]] = []
                for run in new_text_runs:
                    run_text = run.get("text", "")
                    if not run_text:
                        continue
                    layout = encode_with_type3(
                        orig_doc, orig_page, new_page, font_name, run_text
                    )
                    if layout is None:
                        encoded = []
                        break
                    encoded.append((run, layout))
                if encoded:
                    type3_runs = encoded

            font_res: FontResolution | None = None
            fitz_font: fitz.Font | None = None
            if type3_runs is None:
                try:
                    font_res = resolve_font(
                        orig_doc,
                        orig_page,
                        font_name,
                        bold,
                        italic,
                        all_new_text,
                        source_family=face.family,
                        weight=face.weight,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc))
                fitz_font = _get_fitz_font(font_res)

            # Edit bounding box (union of all span bboxes)
            all_bboxes = [s.get("bbox", [0, 0, 0, 0]) for s in spans]
            para_x0 = min(b[0] for b in all_bboxes)
            para_y0 = min(b[1] for b in all_bboxes)
            para_x1 = max(b[2] for b in all_bboxes)
            para_y1 = max(b[3] for b in all_bboxes)
            para_x0, para_x1 = _writable_horizontal_bounds(
                orig_page,
                span_lookup,
                spans,
                para_x0,
                para_y0,
                para_x1,
                para_y1,
                right_to_left,
            )
            available_width = para_x1 - para_x0

            # First line baseline Y
            first_origin = first_span.get("origin")
            baseline_y = float(first_origin[1]) if first_origin else float(para_y0 + dom_size)

            # Compute scale factor
            s = 1.0
            if type3_runs is not None:
                actual_w = sum(
                    layout.width(dom_size * float(run.get("sizeScale", 1.0)))
                    for run, layout in type3_runs
                )
            else:
                actual_w = _runs_total_width(new_text_runs, dom_size, fitz_font, 1.0)
            if actual_w > available_width and overflow_policy == "shrink":
                if type3_runs is not None:
                    steps = int(round((1.0 - SHRINK_MIN_S) / SHRINK_STEP))
                    s = 1.0
                    for i in range(steps + 1):
                        trial = round(1.0 - i * SHRINK_STEP, 6)
                        if trial * dom_size < SHRINK_MIN_SIZE_PT:
                            break
                        s = trial
                        trial_w = sum(
                            layout.width(dom_size * float(run.get("sizeScale", 1.0)) * s)
                            for run, layout in type3_runs
                        )
                        if trial_w <= available_width:
                            break
                    trial_w = sum(
                        layout.width(dom_size * float(run.get("sizeScale", 1.0)) * s)
                        for run, layout in type3_runs
                    )
                    if trial_w > available_width:
                        s = max(0.1, available_width / actual_w)
                        warnings.append(
                            f"Page {page_id}: replacement was reduced to fit its original cell."
                        )
                else:
                    s = _find_shrink_scale(new_text_runs, dom_size, available_width, fitz_font)
                    if _runs_total_width(new_text_runs, dom_size, fitz_font, s) > available_width:
                        s = max(0.1, available_width / actual_w)
                        warnings.append(
                            f"Page {page_id}: replacement was reduced to fit its original cell."
                        )

            if fitz_font is not None:
                line_height = (fitz_font.ascender - fitz_font.descender) * dom_size * s
            else:
                line_height = dom_size * s * 1.2

            # Collect line redaction rects
            line_rects = _line_rect_from_span_ids(span_ids, raw)
            redact_rects.extend(line_rects)
            source_lines = {
                tuple(sid.rsplit(":", 3)[1:3])
                for sid in span_ids
                if len(sid.rsplit(":", 3)) == 4
            }
            single_line = len(source_lines) == 1
            # Family-matched substitutes (embedded or system TTF) already share
            # the source metrics. Recentering them against Helvetica-style
            # ascenders makes edited text look oversized next to neighbors.
            keep_origin_baseline = type3_runs is not None or (
                font_res is not None and font_res.tier == "A"
            )
            if single_line and fitz_font is not None and not keep_origin_baseline:
                baseline_y = _visually_aligned_baseline(
                    new_text_runs,
                    dom_size,
                    s,
                    fitz_font,
                    available_width,
                    line_height,
                    overflow_policy,
                    right_to_left,
                    para_y0,
                    para_y1,
                    baseline_y,
                )

            insertions.append({
                "start_x": para_x0,
                "start_y": baseline_y,
                "right_x": para_x1,
                "runs": new_text_runs,
                "dom_size": dom_size,
                "s": s,
                "font_res": font_res,
                "fitz_font": fitz_font,
                "type3_runs": type3_runs,
                "line_height": line_height,
                "overflow_policy": overflow_policy,
                "right_to_left": right_to_left,
                "single_line": single_line,
            })

        # ── Redact: batch all annotations then apply once per page ────────────
        type3_resource_xrefs: dict[str, int] = {}
        needed_type3 = {
            glyph.resource
            for ins in insertions
            for run, layout in (ins.get("type3_runs") or [])
            for glyph in layout.glyphs
        }
        if needed_type3:
            type3_resource_xrefs = snapshot_type3_resources(new_page, needed_type3)

        strokes = _thin_horizontal_strokes(new_page) if redact_rects else []
        redact_rects = [_clamp_paint_rect(rect, new_page, strokes) for rect in redact_rects]
        bg_by_rect = [
            _sample_bg_rgb(new_page, fitz.Rect(rect))
            for rect in redact_rects
        ]
        for rect in redact_rects:
            # Transparent fill preserves vector cell backgrounds and shading.
            # graphics=NONE below leaves those graphics untouched.
            new_page.add_redact_annot(fitz.Rect(rect), fill=None, cross_out=False)
        if redact_rects:
            new_page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            )
            # Cover leftover glyph outlines inside the text box only. Never
            # paint over nearby table rules — those sit just under cell values.
            for rect, bg in zip(redact_rects, bg_by_rect):
                new_page.draw_rect(fitz.Rect(rect), color=None, fill=bg, width=0)

        if type3_resource_xrefs:
            restore_type3_resources(new_page, type3_resource_xrefs)

        # ── Re-insert ─────────────────────────────────────────────────────────
        for ins in insertions:
            if ins.get("type3_runs"):
                x = ins["start_x"]
                for run, layout in ins["type3_runs"]:
                    fs = ins["dom_size"] * float(run.get("sizeScale", 1.0)) * ins["s"]
                    write_type3_text(
                        new_page,
                        layout,
                        x,
                        ins["start_y"],
                        fs,
                        _hex_to_rgb(run.get("color", "#000000")),
                    )
                    x += layout.width(fs)
                continue
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
                ins["right_to_left"],
                ins["single_line"],
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

    face = source_face_style(doc, page, font_name)
    is_bold = is_bold or face.bold
    is_italic = is_italic or face.italic
    type3_style = type3_face_style(doc, font_name, page)

    type3_width = 0.0
    used_type3 = False
    if all_text and not _is_rtl_text(all_text):
        type3_ok = True
        for run in runs:
            run_text = run.get("text", "")
            if not run_text:
                continue
            layout = encode_with_type3(doc, page, page, font_name, run_text)
            if layout is None:
                type3_ok = False
                break
            type3_width += layout.width(dom_size * float(run.get("sizeScale", 1.0)))
        used_type3 = type3_ok and type3_width > 0

    if used_type3:
        actual_w = type3_width
        font_res = FontResolution(tier="A", fontname=type3_style.face if type3_style else "Type3", css_family=type3_style.family if type3_style else "")
        fitz_font = None
    else:
        try:
            font_res = resolve_font(
                doc,
                page,
                font_name,
                is_bold,
                is_italic,
                all_text,
                source_family=face.family,
                weight=face.weight,
            )
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
            if fitz_font is not None:
                scale_factor = _find_shrink_scale(runs, dom_size, available_width, fitz_font)
                if _runs_total_width(runs, dom_size, fitz_font, scale_factor) > available_width:
                    warning = (
                        f"Text will overflow even at minimum scale ({scale_factor:.0%}). "
                        "Some content may be cut off."
                    )
            else:
                scale_factor = max(0.1, available_width / actual_w) if actual_w else 1.0
                if scale_factor < SHRINK_MIN_S:
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
