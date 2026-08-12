"""
Layout-aware PDF page analyzer.

Builds a typed region model (Table, Box, Paragraph, Image, Divider) from a
fitz.Page by combining:
  - page.get_text("dict") for styled span geometry
  - page.get_drawings()   for ruling lines, filled boxes, table borders
  - page.get_images()     for raster images

The primary target is the Airblue e-ticket format, but the algorithms are
general enough for typical business-document PDFs.

Segmented-h-line table detection
---------------------------------
The Airblue fare table uses thin filled-rectangle segments at each row
separator.  Each row-separator y-position is rendered as N adjacent 1-pt-tall
rectangles, one per column.  The column boundaries are the x0/x1 values where
adjacent segments meet.  This module detects these groups and uses them to
reconstruct a proper table region.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ─── tolerance constants ──────────────────────────────────────────────────────
_MAX_SEG_HEIGHT = 3.0   # pt — max height to treat a path as a "thin h-line"
_MAX_SEG_WIDTH  = 3.0   # pt — max width  to treat a path as a "thin v-line"
_Y_CLUSTER_TOL  = 3.0   # pt — y-positions within this are the same row
_X_CLUSTER_TOL  = 3.0   # pt — x-positions within this are the same column
_COL_MATCH_TOL  = 6.0   # pt — how closely two x-boundary sets must agree
_MIN_TABLE_ROWS = 4      # need at least 4 segmented y-positions (more strict for table detection)
                         # This prevents loose label-value pairs from being treated as tables
_MIN_TABLE_COLS = 2      # need at least this many columns
_TOP_BORDER_LOOKBACK = 30.0  # pt — how far above the first row to look for
                              #       a full-width top border

# column-group splitting (within a y-band)
_COL_GAP_CW_FACTOR = 6.0   # gap > N × avg_char_width in that line → column boundary
_COL_GAP_PAGE_FRAC = 0.08  # gap > 8% of page width → column boundary (floor)
_MAX_TRACK_GAP     = 60.0  # pt — close a column track when y-gap exceeds this


# ─── typed data classes ───────────────────────────────────────────────────────

@dataclass
class Span:
    text:   str
    bold:   bool
    italic: bool
    size:   float
    color:  int   # 0xRRGGBB packed
    x0: float; y0: float; x1: float; y1: float
    # Icon-font glyphs (e.g. Linearicons/FontAwesome PUA codepoints) are
    # rasterized rather than rendered as text — is_icon spans carry PNG
    # bytes instead of meaningful `text`, but keep real coordinates so they
    # flow through paragraph/column/table layout like any other span.
    is_icon: bool = False
    icon_data: Optional[bytes] = None

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class TableCell:
    spans: list[Span] = field(default_factory=list)
    bg_hex: Optional[str] = None   # "RRGGBB" or None


@dataclass
class TableRegion:
    rows: list[list[TableCell]]
    col_xs: list[float]   # sorted column x-boundaries (len = num_cols + 1)
    row_ys: list[float]   # sorted row y-boundaries  (len = num_rows + 1)
    has_borders: bool = True
    y0: float = 0.0
    y1: float = 0.0


@dataclass
class BoxRegion:
    """A filled/bordered rectangle that contains text — e.g. the AGENCY
    DISCOUNT TICKET badge or any notice box drawn in the PDF."""
    spans: list[Span] = field(default_factory=list)
    bg_hex: Optional[str] = None      # "RRGGBB" or None
    border_hex: Optional[str] = None  # "RRGGBB" or None
    x0: float = 0.0; y0: float = 0.0; x1: float = 0.0; y1: float = 0.0

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class ParagraphRegion:
    """Ordered list of text lines; each line is an ordered list of spans."""
    lines: list[list[Span]] = field(default_factory=list)
    y0: float = 0.0

    @property
    def y_center(self) -> float:
        return self.y0

    def dominant_size(self) -> float:
        sizes = [s.size for line in self.lines for s in line if s.text.strip()]
        return max(set(sizes), key=sizes.count) if sizes else 10.0


@dataclass
class ColumnRegion:
    """Two or more side-by-side blocks (same y-range, different x-cluster) —
    usually text, but may include an image (e.g. a barcode beside its
    label). Rendered as a borderless multi-column table."""
    columns: list[list["ParagraphRegion | ImageRegion"]] = field(default_factory=list)
    y0: float = 0.0


@dataclass
class ImageRegion:
    xref: int
    data: bytes
    ext:  str
    x0: float; y0: float; x1: float; y1: float

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


LayoutRegion = TableRegion | BoxRegion | ParagraphRegion | ColumnRegion | ImageRegion


@dataclass
class PageLayout:
    page_num: int
    width:  float
    height: float
    regions: list[LayoutRegion]


# ─── public API ───────────────────────────────────────────────────────────────

def analyze_page(page: fitz.Page, page_num: int) -> PageLayout:
    """Return a PageLayout for the given fitz page."""
    pw, ph = page.rect.width, page.rect.height
    drawings = page.get_drawings()
    raw_dict  = page.get_text("dict", flags=(
        fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
    ))

    all_spans = _extract_spans(raw_dict, page)
    images    = _extract_images(page)
    h_segs    = _collect_h_segments(drawings)
    boxes     = _detect_boxes(drawings)

    tables, consumed_by_table = _detect_tables(h_segs, all_spans, drawings)
    box_regions, consumed_by_box = _assign_boxes(boxes, all_spans, consumed_by_table)

    remaining = [s for s in all_spans if id(s) not in consumed_by_table
                                      and id(s) not in consumed_by_box]

    # Standalone full-width divider rules mark real row boundaries in the
    # source layout (e.g. between "e-ticket / BOOKING REFERENCE" and
    # "Reserved on / Ticketed on" below it). Without this, paragraph-track
    # matching can merge two visually distinct rows into one block just
    # because they happen to share similar x-ranges.
    divider_ys = tuple(_collect_divider_ys(h_segs, pw))

    para_regions = _build_paragraphs(remaining, page_width=pw, divider_ys=divider_ys)
    column_regions, col_consumed, img_col_consumed = _detect_columns(para_regions, images, divider_ys)
    final_paras = [p for p in para_regions if id(p) not in col_consumed]
    final_images = [im for im in images if im.xref not in img_col_consumed]

    # Rasterize leftover vector-graphic clusters (icons, divider lines, the
    # flight-path decoration) not already captured as a table/box, so they
    # aren't silently dropped from the reconstructed document.
    consumed_rects = [fitz.Rect(t.col_xs[0], t.y0, t.col_xs[-1], t.y1) for t in tables]
    consumed_rects += [fitz.Rect(b.x0, b.y0, b.x1, b.y1) for b in box_regions]
    decorative_images = _extract_decorative_graphics(page, drawings, all_spans, consumed_rects)

    regions: list[LayoutRegion] = []
    # Order: images, then tables (detected structure), then paragraphs and columns
    # This preserves images in their position and maintains proper flow
    regions.extend(final_images)
    regions.extend(decorative_images)
    regions.extend(tables)
    regions.extend(box_regions)
    regions.extend(column_regions)
    regions.extend(final_paras)
    regions.sort(key=_region_y)

    return PageLayout(page_num=page_num, width=pw, height=ph, regions=regions)


def analyze_document(doc: fitz.Document) -> list[PageLayout]:
    layouts = []
    for i, page in enumerate(doc):
        try:
            layouts.append(analyze_page(page, i))
        except Exception:
            logger.exception("layout_analyzer: error on page %d", i)
            layouts.append(PageLayout(page_num=i,
                                      width=page.rect.width,
                                      height=page.rect.height,
                                      regions=[]))
    return layouts


# ─── drawing helpers ──────────────────────────────────────────────────────────

def _rgb_to_hex(rgb_tuple) -> Optional[str]:
    """Convert (r,g,b) float 0-1 tuple to 'RRGGBB' hex string."""
    if rgb_tuple is None:
        return None
    r, g, b = rgb_tuple[:3]
    return "{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def _collect_h_segments(drawings) -> list[tuple[float, float, float]]:
    """Return all thin horizontal segments as (y_center, x0, x1).

    Handles both thin FILLED rectangles (common in HTML->PDF exports, where
    a divider or table border becomes a filled bar) and zero-height
    STROKED lines (common in PDFs built with a drawing API, where a rule is
    a literal line-draw operator) -- a source PDF's dividers/table borders
    can use either convention. A horizontal stroked line's bounding box is
    legitimately zero-height, which fitz.Rect.is_empty() flags as "empty";
    that used to make this function skip it entirely, silently failing to
    detect any divider/table line drawn that way.
    """
    segs = []
    for path in drawings:
        r = fitz.Rect(path["rect"])
        if r.width <= 0:
            continue  # genuinely degenerate (zero/negative width), not just zero-height
        # Treat the whole path as an h-segment if it's thin and wide enough
        if r.height <= _MAX_SEG_HEIGHT and r.width > 5:
            segs.append((r.y0 + r.height / 2, r.x0, r.x1))
            continue
        # Also scan 're' (rect) and 'l' (line) items inside the path, in
        # case they differ from the outer rect (e.g. a compound path).
        for item in path.get("items", []):
            if item[0] == "re":
                rr = fitz.Rect(item[1])
                if rr.height <= _MAX_SEG_HEIGHT and rr.width > 5:
                    segs.append((rr.y0 + rr.height / 2, rr.x0, rr.x1))
            elif item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= _MAX_SEG_HEIGHT and abs(p1.x - p2.x) > 5:
                    x0, x1 = sorted((p1.x, p2.x))
                    segs.append(((p1.y + p2.y) / 2, x0, x1))
    # Deduplicate by rounding
    seen = set()
    result = []
    for y, x0, x1 in segs:
        key = (round(y, 1), round(x0, 1), round(x1, 1))
        if key not in seen:
            seen.add(key)
            result.append((y, x0, x1))
    return result


def _collect_divider_ys(h_segs: list[tuple[float, float, float]], page_width: float) -> list[float]:
    """Return y-positions of standalone full/near-full-width horizontal
    divider rules (not table row separators — those are handled separately
    by _detect_tables). These mark real row boundaries in the source PDF
    (e.g. between a header row and the row below it) and are used as hard
    boundaries so paragraph-track/column clustering doesn't merge content
    from visually distinct rows just because they share similar x-ranges."""
    by_y = _cluster_y(h_segs)
    dividers = []
    for y, segs in by_y.items():
        if len(segs) != 1:
            continue  # a group of segments at one y is a table row separator, not a rule
        x0, x1 = segs[0]
        if (x1 - x0) > 0.5 * page_width:
            dividers.append(y)
    return sorted(dividers)


def _detect_boxes(drawings) -> list[dict]:
    """Find filled or bordered rectangular paths large enough to be boxes.
    Returns list of dicts: {rect, bg_hex, border_hex}."""
    boxes = []
    for path in drawings:
        r = fitz.Rect(path["rect"])
        if r.is_empty or r.width < 10 or r.height < 5:
            continue
        # Skip very thin horizontal / vertical rules
        if r.height <= _MAX_SEG_HEIGHT or r.width <= _MAX_SEG_WIDTH:
            continue
        fill   = path.get("fill")
        stroke = path.get("color")
        if fill is None and stroke is None:
            continue
        # Must have either a non-white fill or a visible stroke
        bg_hex     = _rgb_to_hex(fill)
        border_hex = _rgb_to_hex(stroke)
        # Skip pure white fill with no stroke (it's a page background, not a box)
        if bg_hex in (None, "ffffff") and border_hex is None:
            continue
        boxes.append({
            "rect": r,
            "bg_hex": bg_hex if bg_hex != "ffffff" else None,
            "border_hex": border_hex,
        })
    return boxes


# ─── span extraction ─────────────────────────────────────────────────────────

_PUA_RANGE = [(0xE000, 0xF8FF), (0xF0000, 0x10FFFF)]


def _strip_pua(text: str) -> str:
    return "".join(
        ch for ch in text
        if not any(lo <= ord(ch) <= hi for lo, hi in _PUA_RANGE)
    )


def _flags_to_style(flags: int, font_name: str = "") -> tuple[bool, bool]:
    bold   = bool(flags & (1 << 4))
    italic = bool(flags & (1 << 1))
    if font_name and not (bold or italic):
        fn = font_name.upper()
        bold   = ("BOLD" in fn or fn.endswith(",BD") or "-BD" in fn
                  or fn.endswith("-B") or ",BOLD" in fn)
        italic = ("ITALIC" in fn or "OBLIQUE" in fn
                  or "-IT" in fn or "-OB" in fn or ",IT" in fn)
    return bold, italic


def _is_pua(ch: str) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in _PUA_RANGE)


def _rasterize_icon_span(page: fitz.Page, span_dict: dict) -> Optional[Span]:
    """Icon-font glyph (Linearicons/FontAwesome PUA codepoint) → an icon
    Span carrying a small rasterized PNG instead of text. Rendering the
    actual glyph doesn't require the source icon font to be installed."""
    b = span_dict["bbox"]
    rect = fitz.Rect(b)
    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return None
    pad = 0.75
    clip = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad) & page.rect
    try:
        pix = page.get_pixmap(clip=clip, dpi=300, alpha=True)
        data = pix.tobytes("png")
    except Exception:
        return None
    return Span(
        text="", bold=False, italic=False,
        size=span_dict.get("size", 10.0), color=0,
        x0=clip.x0, y0=clip.y0, x1=clip.x1, y1=clip.y1,
        is_icon=True, icon_data=data,
    )


def _extract_spans(raw_dict: dict, page: Optional[fitz.Page] = None) -> list[Span]:
    """Extract all Span objects from page.get_text('dict') output.

    When `page` is given, icon-font glyphs (spans that are entirely PUA
    codepoints — e.g. a Linearicons/FontAwesome symbol) are rasterized into
    icon Spans instead of being silently dropped by _strip_pua.
    """
    spans: list[Span] = []
    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for s in line.get("spans", []):
                raw_text = s.get("text", "")
                text = _strip_pua(raw_text)
                if not text:
                    if page is not None and any(_is_pua(ch) for ch in raw_text):
                        icon_span = _rasterize_icon_span(page, s)
                        if icon_span is not None:
                            spans.append(icon_span)
                    continue
                # Drop zero-width invisible glyphs
                b = s["bbox"]
                if not text.strip() and (b[2] - b[0]) < 0.1:
                    continue
                flags = s.get("flags", 0)
                bold, italic = _flags_to_style(flags, s.get("font", ""))
                color_int = s.get("color", 0) or 0
                spans.append(Span(
                    text=text, bold=bold, italic=italic,
                    size=s.get("size", 10.0), color=color_int,
                    x0=b[0], y0=b[1], x1=b[2], y1=b[3],
                ))
    return spans


# ─── image extraction ─────────────────────────────────────────────────────────

def _extract_images(page: fitz.Page) -> list[ImageRegion]:
    doc = page.parent
    result: list[ImageRegion] = []
    for item in page.get_images(full=True):
        xref = item[0]
        smask = item[1]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        if not rects:
            continue
        try:
            # extract_image() returns only the base image. PDFs commonly store
            # transparency in a separate soft mask; dropping it turns transparent
            # logo pixels black when Word renders the extracted bitmap.
            pix = fitz.Pixmap(doc, xref)
            if smask:
                mask = fitz.Pixmap(doc, smask)
                pix = fitz.Pixmap(pix, mask)
            if pix.n > 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            image_data = pix.tobytes("png")
        except Exception:
            continue
        if not image_data:
            continue
        # The same image xref can be painted more than once on a page. Preserve
        # every placement instead of silently keeping only the first rectangle.
        for r in rects:
            result.append(ImageRegion(
                xref=xref, data=image_data, ext="png",
                x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1,
            ))
    return result


# ─── decorative vector-graphics extraction ───────────────────────────────────
#
# page.get_images() only returns raster images (photos/PNGs embedded in the
# PDF) — it misses everything drawn with vector paths: small icons, thin
# divider lines, and decorative shapes like a dotted flight-path line with a
# plane glyph. Those are only visible via page.get_drawings(), and outside of
# table-border/box detection above, nothing else in this module looks at
# them, so they were silently dropped from the reconstructed document. This
# rasterizes leftover small vector-drawing clusters into images instead.

_MAX_DECOR_W  = 460.0  # pt — cap for icon/decoration clusters (not full-width)
_MAX_DECOR_H  = 45.0   # pt — cap for icon/decoration clusters
_MAX_LINE_H   = 3.0    # pt — thin lines/dividers are exempt from _MAX_DECOR_W
_MIN_DECOR_AREA = 4.0  # pt^2 — drop near-zero-area stray path fragments
_DECOR_MERGE_GAP = 6.0  # pt — merge drawing fragments within this distance
                         # into one cluster (so a multi-path icon glyph
                         # becomes a single image instead of several)


def _merge_close_rects(rects: list["fitz.Rect"], gap: float) -> list["fitz.Rect"]:
    """Iteratively union rects that overlap or lie within `gap` of each
    other, so fragments of one icon/shape collapse into one bounding rect."""
    rects = list(rects)
    changed = True
    while changed:
        changed = False
        merged: list[fitz.Rect] = []
        used = [False] * len(rects)
        for i, r1 in enumerate(rects):
            if used[i]:
                continue
            cur = fitz.Rect(r1)
            used[i] = True
            for j in range(i + 1, len(rects)):
                if used[j]:
                    continue
                expanded = fitz.Rect(cur.x0 - gap, cur.y0 - gap, cur.x1 + gap, cur.y1 + gap)
                if expanded.intersects(rects[j]):
                    cur |= rects[j]
                    used[j] = True
                    changed = True
            merged.append(cur)
        rects = merged
    return rects


def _extract_decorative_graphics(
    page: fitz.Page,
    drawings,
    all_spans: list[Span],
    consumed_rects: list["fitz.Rect"],
) -> list[ImageRegion]:
    """Rasterize leftover small vector-graphic clusters (icons, divider
    lines, decorative shapes) not already represented by a detected table or
    box, so they show up in the output instead of being dropped."""
    page_rect = page.rect
    text_rects = [fitz.Rect(s.x0, s.y0, s.x1, s.y1) for s in all_spans]

    candidates: list[fitz.Rect] = []
    for path in drawings:
        r = fitz.Rect(path["rect"])
        if r.is_empty or r.width * r.height < _MIN_DECOR_AREA:
            continue
        if any(cr.contains(r) for cr in consumed_rects):
            continue  # already represented as a table border or box
        if any(r.intersects(tr) for tr in text_rects):
            continue  # overlaps real text — too risky to rasterize (dup/occlude)
        candidates.append(r)

    if not candidates:
        return []

    regions: list[ImageRegion] = []
    for i, rect in enumerate(_merge_close_rects(candidates, _DECOR_MERGE_GAP)):
        w, h = rect.width, rect.height
        if w <= 0 or h <= 0:
            continue
        if w > 0.9 * page_rect.width and h > 0.9 * page_rect.height:
            continue  # whole-page background fill
        is_vertical_line = w <= _MAX_LINE_H and h > _MAX_LINE_H
        if is_vertical_line:
            # A column-separator rule from the source PDF's side-by-side
            # layout. Our reconstruction is single-column top-to-bottom, so
            # this would render as an orphaned floating hairline disconnected
            # from whatever it used to sit between — worse than omitting it.
            continue
        is_thin_line = h <= _MAX_LINE_H
        if is_thin_line:
            if w > page_rect.width * 0.98:
                continue  # true full-bleed rule, not a meaningful divider
        elif w > _MAX_DECOR_W or h > _MAX_DECOR_H:
            continue  # too large to be an icon/decoration — leave it alone

        pad = 1.0
        clip = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad) & page_rect
        try:
            pix = page.get_pixmap(clip=clip, dpi=200, alpha=True)
            data = pix.tobytes("png")
        except Exception:
            logger.debug("failed to rasterize decorative cluster at %s", rect)
            continue
        regions.append(ImageRegion(
            xref=-(1000 + i),  # synthetic — these have no real PDF xref
            data=data, ext="png",
            x0=clip.x0, y0=clip.y0, x1=clip.x1, y1=clip.y1,
        ))
    return regions


# ─── table detection ─────────────────────────────────────────────────────────

def _cluster_y(segs):
    """Group (y, x0, x1) triples by y-position (within _Y_CLUSTER_TOL)."""
    by_y: dict[float, list[tuple[float, float]]] = {}
    for y, x0, x1 in segs:
        matched = None
        for ky in list(by_y.keys()):
            if abs(y - ky) <= _Y_CLUSTER_TOL:
                matched = ky
                break
        if matched is None:
            by_y[y] = [(x0, x1)]
        else:
            by_y[matched].append((x0, x1))
    return by_y


def _col_structure(seg_list: list[tuple[float, float]]) -> tuple[float, ...]:
    """Return a sorted tuple of all unique x-boundaries from a segment list."""
    xs: set[int] = set()
    for x0, x1 in seg_list:
        xs.add(round(x0))
        xs.add(round(x1))
    return tuple(sorted(xs))


def _structures_match(a: tuple, b: tuple) -> bool:
    """True if two column-structure tuples have the same x-boundaries
    (within _COL_MATCH_TOL) and the same number of entries."""
    if len(a) != len(b):
        return False
    return all(abs(xa - xb) <= _COL_MATCH_TOL for xa, xb in zip(a, b))


def _detect_tables(
    h_segs: list[tuple[float, float, float]],
    all_spans: list[Span],
    drawings,
) -> tuple[list[TableRegion], set[int]]:
    """
    Detect tables from segmented horizontal lines.

    The algorithm:
    1.  Cluster all h-segments by y-position.
    2.  For y-positions with >=2 segments (i.e. NOT a single full-width line),
        extract the column-boundary structure.
    3.  Group y-positions whose column structure matches — they form a table.
    4.  For each group, find the top border (a single full-width line just
        above the first segmented y).
    5.  Extract spans into cells.
    """
    consumed: set[int] = set()
    tables: list[TableRegion] = []

    by_y = _cluster_y(h_segs)
    if not by_y:
        return tables, consumed

    # Separate "segmented" y-positions (multiple segments → column info)
    # from single full-width lines (borders / dividers)
    segmented: dict[float, tuple[float, ...]] = {}
    full_width_ys: list[float] = []
    page_width = max((x1 for _, x0, x1 in h_segs), default=0.0)

    for y, segs in sorted(by_y.items()):
        struct = _col_structure(segs)
        total_span = max(x1 for _, x1 in segs) - min(x0 for x0, _ in segs)
        if len(struct) >= 3 and total_span > 10:  # at least 2 columns
            segmented[y] = struct
        elif len(segs) == 1 and segs[0][1] - segs[0][0] > 100:
            full_width_ys.append(y)

    if not segmented:
        return tables, consumed

    # Group consecutive y-positions that share the same column structure
    sorted_ys = sorted(segmented.keys())
    groups: list[list[float]] = []
    current = [sorted_ys[0]]
    for y in sorted_ys[1:]:
        if _structures_match(segmented[current[-1]], segmented[y]):
            current.append(y)
        else:
            if len(current) >= _MIN_TABLE_ROWS - 1:
                groups.append(current)
            current = [y]
    if len(current) >= _MIN_TABLE_ROWS - 1:
        groups.append(current)

    # Build a TableRegion for each group
    filled_rects = [
        (fitz.Rect(p["rect"]), p.get("fill"))
        for p in drawings
        if p.get("fill") and fitz.Rect(p["rect"]).height > 3
    ]

    for group in groups:
        col_xs_raw = segmented[group[0]]
        if len(col_xs_raw) < _MIN_TABLE_COLS + 1:
            continue

        col_xs = list(col_xs_raw)

        # Find top border: a full-width line just above the first group y
        top_y = group[0]
        best_top = top_y  # fallback: no separate top border
        for fy in full_width_ys:
            if fy < top_y and (top_y - fy) <= _TOP_BORDER_LOOKBACK:
                if fy > best_top - _TOP_BORDER_LOOKBACK:
                    best_top = fy

        bottom_y = group[-1]
        row_ys = [best_top] + group  # row boundaries

        # Determine cell background colors from filled rects
        def _cell_bg(ry0, ry1, cx0, cx1) -> Optional[str]:
            for r, fill in filled_rects:
                if fill is None:
                    continue
                if (r.y0 <= ry0 + 2 and r.y1 >= ry1 - 2
                        and r.x0 <= cx0 + 2 and r.x1 >= cx1 - 2):
                    return _rgb_to_hex(fill)
            return None

        # Extract spans for each row × column
        rows: list[list[TableCell]] = []
        for ri in range(len(row_ys) - 1):
            ry0, ry1 = row_ys[ri], row_ys[ri + 1]
            row: list[TableCell] = []
            for ci in range(len(col_xs) - 1):
                cx0, cx1 = col_xs[ci], col_xs[ci + 1]
                cell_spans = [
                    s for s in all_spans
                    if s.y0 >= ry0 - 2 and s.y1 <= ry1 + 2
                    and s.x_center >= cx0 and s.x_center < cx1
                ]
                bg = _cell_bg(ry0, ry1, cx0, cx1)
                cell = TableCell(spans=cell_spans, bg_hex=bg)
                row.append(cell)
                for s in cell_spans:
                    consumed.add(id(s))
            rows.append(row)

        tables.append(TableRegion(
            rows=rows, col_xs=col_xs, row_ys=row_ys,
            has_borders=True, y0=best_top, y1=bottom_y,
        ))
        logger.debug(
            "table detected: rows=%d cols=%d y=%.0f-%.0f",
            len(rows), len(col_xs) - 1, best_top, bottom_y,
        )

    return tables, consumed


# ─── styled box detection ─────────────────────────────────────────────────────

def _assign_boxes(
    box_dicts: list[dict],
    all_spans: list[Span],
    already_consumed: set[int],
) -> tuple[list[BoxRegion], set[int]]:
    """Match filled/bordered drawing rects to their contained text spans."""
    consumed: set[int] = set()
    regions: list[BoxRegion] = []

    # Sort boxes smallest-first so nested boxes are handled correctly
    boxes_sorted = sorted(box_dicts, key=lambda b: b["rect"].width * b["rect"].height)

    for bd in boxes_sorted:
        r = bd["rect"]
        contained = [
            s for s in all_spans
            if id(s) not in already_consumed
            and id(s) not in consumed
            and r.x0 - 2 <= s.x0 and s.x1 <= r.x1 + 2
            and r.y0 - 2 <= s.y0 and s.y1 <= r.y1 + 2
        ]
        if not contained:
            continue
        br = BoxRegion(
            spans=contained,
            bg_hex=bd["bg_hex"],
            border_hex=bd["border_hex"],
            x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1,
        )
        regions.append(br)
        for s in contained:
            consumed.add(id(s))

    return regions, consumed


# ─── paragraph building ───────────────────────────────────────────────────────

_LINE_TOL = 3.0      # pt — y-distance within which spans are on the same line
_PARA_GAP = 1.5      # × median line spacing → new paragraph


def _split_into_col_groups(spans: list[Span], page_width: float) -> list[list[Span]]:
    """Split a sorted (by x0) line of spans at large x-gaps (column boundaries).

    A gap is a column boundary when it exceeds both:
    - _COL_GAP_CW_FACTOR × local average char width, and
    - _COL_GAP_PAGE_FRAC × page_width (floor that prevents false splits for tiny text)
    The larger of the two is used as the threshold.
    """
    if len(spans) <= 1:
        return [spans] if spans else []

    # Estimate average character width for this line
    char_count = sum(max(1, len(s.text.strip())) for s in spans)
    char_width_sum = sum(s.width for s in spans if s.text.strip())
    avg_cw = max(char_width_sum / char_count if char_count > 0 else 6.0, 4.0)

    threshold = max(_COL_GAP_CW_FACTOR * avg_cw, _COL_GAP_PAGE_FRAC * page_width)

    groups: list[list[Span]] = [[spans[0]]]
    for si in range(1, len(spans)):
        gap = spans[si].x0 - spans[si - 1].x1
        if gap >= threshold:
            groups.append([])
        groups[-1].append(spans[si])

    return [g for g in groups if g]


def _assemble_paragraphs(
    line_pairs: list[tuple[float, list[Span]]],
) -> list[ParagraphRegion]:
    """Convert (y_center, spans) pairs — already sorted by y — into ParagraphRegions,
    splitting at large vertical gaps."""
    if not line_pairs:
        return []

    line_ys = [y for y, _ in line_pairs]
    lines   = [spans for _, spans in line_pairs]

    gaps = [line_ys[i + 1] - line_ys[i] for i in range(len(line_ys) - 1)]
    if not gaps:
        y0 = lines[0][0].y0 if lines[0] else 0.0
        return [ParagraphRegion(lines=lines, y0=y0)]

    sorted_gaps = sorted(gaps)
    median_gap  = sorted_gaps[len(sorted_gaps) // 2]
    threshold   = max(median_gap * _PARA_GAP, 4.0)

    paragraphs: list[ParagraphRegion] = []
    current_lines: list[list[Span]] = [lines[0]]
    for i, gap in enumerate(gaps):
        if gap > threshold:
            y0 = current_lines[0][0].y0 if current_lines[0] else 0.0
            paragraphs.append(ParagraphRegion(lines=current_lines, y0=y0))
            current_lines = []
        current_lines.append(lines[i + 1])
    if current_lines:
        y0 = current_lines[0][0].y0 if current_lines[0] else 0.0
        paragraphs.append(ParagraphRegion(lines=current_lines, y0=y0))
    return paragraphs


def _build_paragraphs(spans: list[Span],
                      page_width: float = 595.0,
                      divider_ys: tuple[float, ...] = ()) -> list[ParagraphRegion]:
    """Cluster remaining spans into ParagraphRegion objects.

    Within each y-band, spans are split at large x-gaps into independent column
    groups (_split_into_col_groups).  All bands — single-group and multi-group —
    are then processed in y-order through a single IoU-based track-matching loop.
    Processing everything together in y-order lets naturally-appearing column
    elements (e.g. a header field that has no left/right neighbours at its y)
    establish their own tracks before later multi-band rows arrive, so they
    correctly attract vertically-adjacent same-column items by IoU rather than
    being misassigned to a track created by a later row.

    Wide "full-page" spans (whose x-extent is > _WIDE_SPAN_FACTOR times the
    page width) are rejected from joining narrow column tracks; they become
    standalone ParagraphRegions instead.
    """
    if not spans:
        return []

    # 1. Cluster spans into y-bands by y-center proximity
    y_bands: list[list[Span]] = []
    for span in sorted(spans, key=lambda s: (s.y_center, s.x0)):
        placed = False
        for band in reversed(y_bands):
            rep_y = sum(s.y_center for s in band) / len(band)
            if abs(span.y_center - rep_y) <= _LINE_TOL:
                band.append(span)
                placed = True
                break
        if not placed:
            y_bands.append([span])
    for band in y_bands:
        band.sort(key=lambda s: s.x0)
    y_bands.sort(key=lambda b: sum(s.y_center for s in b) / len(b))

    # 2. Split each y-band into column groups
    split_bands: list[tuple[float, list[list[Span]]]] = []
    for band in y_bands:
        band_y = sum(s.y_center for s in band) / len(band)
        groups = _split_into_col_groups(band, page_width)
        split_bands.append((band_y, groups))

    # 3. Fast path: no multi-column splits anywhere
    if all(len(groups) == 1 for _, groups in split_bands):
        return _assemble_paragraphs([(y, groups[0]) for y, groups in split_bands])

    # 4. One-phase: assign every column group to an x-matching track in y-order.
    #
    #    Match score = IoU of x-ranges.  Reject a match if the incoming group is
    #    significantly wider than the established track (ratio > _WIDE_RATIO) —
    #    that indicates a full-width element that spans multiple columns.
    _IOU_THRESHOLD  = 0.40   # minimum IoU to join an existing track
    _WIDE_RATIO     = 2.5    # reject if group_width > WIDE_RATIO × track_width
    _NARROW_RATIO   = 2.2    # reject if track_width > NARROW_RATIO × group_width

    active_tracks: list[dict] = []
    closed_tracks: list[dict] = []

    for band_y, groups in split_bands:
        still, newly_closed = [], []
        for t in active_tracks:
            crosses_divider = any(t["last_y"] < dy <= band_y for dy in divider_ys)
            gap_too_big = band_y - t["last_y"] > _MAX_TRACK_GAP
            (newly_closed if (gap_too_big or crosses_divider) else still).append(t)
        active_tracks = still
        closed_tracks.extend(newly_closed)

        matched: set[int] = set()
        for group in groups:
            gx0 = min(s.x0 for s in group)
            gx1 = max(s.x1 for s in group)
            group_w = max(gx1 - gx0, 1.0)

            best_t: Optional[dict] = None
            best_score = 0.0
            for t in active_tracks:
                if id(t) in matched:
                    continue
                track_w = max(t["x1"] - t["x0"], 1.0)
                if group_w > _WIDE_RATIO * track_w:
                    continue  # group too wide to join this narrow track
                if track_w > _NARROW_RATIO * group_w:
                    continue  # track too wide — narrow group belongs to its own column
                overlap = min(gx1, t["x1"]) - max(gx0, t["x0"])
                union   = max(gx1, t["x1"]) - min(gx0, t["x0"])
                if union <= 0:
                    continue
                score = overlap / union
                if score > _IOU_THRESHOLD and score > best_score:
                    best_score = score
                    best_t = t

            if best_t is None:
                best_t = {
                    "x0": gx0, "x1": gx1,
                    "last_y": band_y,
                    "line_pairs": [],
                }
                active_tracks.append(best_t)

            matched.add(id(best_t))
            best_t["line_pairs"].append((band_y, group))
            best_t["last_y"] = band_y
            best_t["x0"]     = min(best_t["x0"], gx0)
            best_t["x1"]     = max(best_t["x1"], gx1)

    all_tracks = closed_tracks + active_tracks

    # 5. Build ParagraphRegions from each track
    all_paras: list[ParagraphRegion] = []
    for t in all_tracks:
        all_paras.extend(_assemble_paragraphs(t["line_pairs"]))
    return all_paras


# ─── multi-column detection ───────────────────────────────────────────────────

_COL_OVERLAP_FRAC = 0.5   # two paragraphs are "same row" if y-overlap / shorter > this
_COL_MIN_X_GAP   = 40.0   # pt — minimum x-gap between columns


def _item_bbox(item) -> tuple[float, float, float, float]:
    """Return (x0, y0, x1, y1) for a ParagraphRegion or ImageRegion, so both
    can be compared uniformly by column detection below."""
    if isinstance(item, ImageRegion):
        return (item.x0, item.y0, item.x1, item.y1)
    xs0 = [s.x0 for line in item.lines for s in line]
    xs1 = [s.x1 for line in item.lines for s in line]
    ys0 = [s.y0 for line in item.lines for s in line]
    ys1 = [s.y1 for line in item.lines for s in line]
    if not xs0:
        return (0.0, item.y0, 0.0, item.y0)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _item_y_overlap_frac(a, b) -> float:
    ax0, ay0, ax1, ay1 = _item_bbox(a)
    bx0, by0, bx1, by1 = _item_bbox(b)
    overlap = min(ay1, by1) - max(ay0, by0)
    shorter = min(ay1 - ay0, by1 - by0)
    return overlap / shorter if shorter > 1 else 0.0


def _item_x_iou(a, b) -> float:
    ax0, _, ax1, _ = _item_bbox(a)
    bx0, _, bx1, _ = _item_bbox(b)
    overlap = min(ax1, bx1) - max(ax0, bx0)
    union = max(ax1, bx1) - min(ax0, bx0)
    return max(overlap, 0.0) / union if union > 0 else 0.0


def _row_band_index(y_center: float, divider_ys: tuple[float, ...]) -> int:
    """Which divider-bounded row-band a y-coordinate's center falls into."""
    idx = 0
    for dy in divider_ys:
        if y_center >= dy:
            idx += 1
        else:
            break
    return idx


def _detect_columns(
    paras: list[ParagraphRegion],
    images: Optional[list[ImageRegion]] = None,
    divider_ys: tuple[float, ...] = (),
) -> tuple[list[ColumnRegion], set[int], set[int]]:
    """
    Find items (paragraphs and/or raster images, e.g. a barcode sitting
    beside a text label) that are side-by-side (same y-range, different x
    clusters). Returns ColumnRegions, the set of consumed ParagraphRegion
    ids, and the set of consumed ImageRegion xrefs.
    """
    items: list = [*paras, *(images or [])]

    consumed_para_ids: set[int] = set()
    consumed_image_xrefs: set[int] = set()
    column_regions: list[ColumnRegion] = []

    used = set()
    for i, p1 in enumerate(items):
        if id(p1) in used:
            continue
        p1_band = _row_band_index((_item_bbox(p1)[1] + _item_bbox(p1)[3]) / 2, divider_ys)
        siblings = [p1]
        for j, p2 in enumerate(items):
            if i == j or id(p2) in used:
                continue
            # A tall item (e.g. a logo) can geometrically overlap two
            # divider-separated rows at once; require both items' *centers*
            # to land in the same row-band so it's only matched to the row
            # it predominantly belongs to, not whichever row's pairwise
            # comparison happens to run first.
            p2_band = _row_band_index((_item_bbox(p2)[1] + _item_bbox(p2)[3]) / 2, divider_ys)
            if p2_band != p1_band:
                continue
            if _item_y_overlap_frac(p1, p2) >= _COL_OVERLAP_FRAC:
                x_gap = abs(_item_bbox(p2)[0] - _item_bbox(p1)[0])
                if x_gap >= _COL_MIN_X_GAP:
                    siblings.append(p2)

        if len(siblings) < 2:
            continue

        # An image only joins a column alongside at least one real paragraph
        # (e.g. a barcode beside "BOOKING REFERENCE"). Two side-by-side
        # images with no text between them are already handled fine as
        # standalone stacked images, so leave those alone.
        if not any(isinstance(s, ParagraphRegion) for s in siblings):
            continue

        # Sort seed siblings left to right, then extend each x-track downward.
        # Requiring y-overlap is useful for identifying that columns exist, but
        # later blocks in a column may continue after a shorter sibling column
        # has ended (a common resume layout).
        siblings.sort(key=lambda s: _item_bbox(s)[0])
        y0 = min(_item_bbox(s)[1] for s in siblings)
        col_groups: list[list] = [[s] for s in siblings]
        sibling_ids = {id(s) for s in siblings}

        candidates = [
            item for item in items
            if id(item) not in used
            and id(item) not in sibling_ids
            and _row_band_index(
                (_item_bbox(item)[1] + _item_bbox(item)[3]) / 2,
                divider_ys,
            ) == p1_band
            and _item_bbox(item)[1] >= y0
        ]
        for item in sorted(candidates, key=lambda candidate: _item_bbox(candidate)[1]):
            scores = [_item_x_iou(item, group[0]) for group in col_groups]
            best_col = max(range(len(scores)), key=scores.__getitem__)
            if scores[best_col] >= 0.40:
                col_groups[best_col].append(item)

        column_regions.append(ColumnRegion(columns=col_groups, y0=y0))
        for s in (item for group in col_groups for item in group):
            used.add(id(s))
            if isinstance(s, ParagraphRegion):
                consumed_para_ids.add(id(s))
            else:
                consumed_image_xrefs.add(s.xref)

    return column_regions, consumed_para_ids, consumed_image_xrefs


# ─── region ordering helper ───────────────────────────────────────────────────

def _region_y(r: LayoutRegion) -> float:
    if isinstance(r, TableRegion):
        return r.y0
    if isinstance(r, BoxRegion):
        return r.y0
    if isinstance(r, ImageRegion):
        return r.y0
    if isinstance(r, ParagraphRegion):
        return r.y0
    if isinstance(r, ColumnRegion):
        return r.y0
    return 0.0
