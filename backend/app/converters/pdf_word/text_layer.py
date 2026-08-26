"""
PyMuPDF-based text extraction layer for PDF → DOCX conversion.

WHY this exists (and why the previous pdf2docx approach was insufficient)
------------------------------------------------------------------------
pdf2docx uses PyMuPDF internally but reconstructs text by iterating font-run
boundaries without gap/position awareness.  The concrete failure modes are:

  Bug 1 — WORD-SPACING LOSS
    Type3 PDFs store each glyph-set (word) as a separate span with a
    *different* font reference, even for a single weight/style.  A " " space
    is its own span with yet another font ref.  pdf2docx treats font-ref
    changes as style boundaries and emits each run separately, dropping the
    space span when the run has the same visual style (bold/italic/color) as
    its neighbours, producing "AIRBLUELIMITED" instead of "AIRBLUE LIMITED".

    Fix: use get_text("dict") which returns every span with its exact bbox.
    We concatenate spans on the same visual line, inserting a synthetic space
    whenever the horizontal gap between span-x1 and next-span-x0 exceeds
    GAP_SPACE_THRESHOLD * avg-char-width (proportional, not fixed pixels).

  Bug 2 — SPAN ORDERING / SCRAMBLED TEXT
    pdf2docx processes blocks in PDF content-stream order (z-order), which
    can differ from left-to-right reading order when graphics and text items
    interleave.  Phone numbers and multi-column rows come out scrambled.

    Fix: cluster all spans from a page into visual lines by baseline proximity,
    then sort each line's spans strictly by x0.  Lines are then sorted by
    their median y-coordinate.

  Bug 3 — TEXT CLIPPED / DROPPED NEAR OVERLAPPING GRAPHICS
    pdf2docx computes per-block clip regions from image bounding boxes and
    suppresses text whose bbox overlaps an image block, truncating e.g.
    "VQFDCO" → "VQFDC" when a barcode occupies the right portion of the area.

    Fix: extract ALL text spans first, completely independently of image
    positions.  Image positions are tracked in a separate list and used only
    at the DOCX-rendering stage (placing inline images).  No text is ever
    suppressed by image bbox intersection.

  Bug 4 — SHAPE-EMBEDDED / BADGE TEXT SKIPPED
    pdf2docx walks only standard text blocks.  Text drawn inside filled
    rectangles (badges like "AGENCY DISCOUNT TICKET") can appear as a block
    whose bbox falls entirely within an image-type block bbox, so pdf2docx's
    image-first pass shadows it and skips it in the text pass.

    Fix: annotation objects (page.annots()) and form-widget values
    (page.widgets()) are walked explicitly and merged into the span list
    before any ordering step.  Text-type blocks that overlap image blocks
    are preserved, not suppressed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import fitz

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tuning constants                                                             #
# --------------------------------------------------------------------------- #

# Insert a synthetic " " when the gap between two adjacent same-line spans
# exceeds this multiple of the current span's average character width.
# 0.15 is conservative enough to catch real word gaps without generating
# false spaces inside tight ligature runs.
GAP_SPACE_THRESHOLD: float = 0.15

# Two spans belong to the same visual line when their y-centres are within
# this multiple of the median span height.
BASELINE_TOLERANCE_FACTOR: float = 0.55

# Two spans in the same line belong to different columns when their horizontal
# gap exceeds this multiple of the median character width for that line.
# Such column gaps are emitted as paragraph breaks rather than spaces.
COLUMN_GAP_FACTOR: float = 6.0

# Minimum number of aligned column pairs across rows to call it a table.
TABLE_MIN_ROWS: int = 2
TABLE_MIN_COLS: int = 2

# Column x-positions must agree within this many points to be "aligned".
TABLE_COL_TOL: float = 6.0


# --------------------------------------------------------------------------- #
# Public data types                                                            #
# --------------------------------------------------------------------------- #

@dataclass
class TextSpan:
    """A single styled text fragment with exact page coordinates."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float          # font size in points
    bold: bool = False
    italic: bool = False
    color: int = 0       # packed 0xRRGGBB


@dataclass
class TextLine:
    """Ordered spans that share a visual baseline, already in reading order."""
    spans: list[TextSpan]

    @property
    def x0(self) -> float:
        return self.spans[0].x0 if self.spans else 0.0

    @property
    def x1(self) -> float:
        return self.spans[-1].x1 if self.spans else 0.0

    @property
    def y_center(self) -> float:
        ys = [(s.y0 + s.y1) / 2 for s in self.spans]
        return sum(ys) / len(ys) if ys else 0.0

    @property
    def height(self) -> float:
        if not self.spans:
            return 0.0
        return max(s.y1 for s in self.spans) - min(s.y0 for s in self.spans)

    @property
    def dominant_size(self) -> float:
        if not self.spans:
            return 10.0
        by_len = sorted(self.spans, key=lambda s: len(s.text), reverse=True)
        return by_len[0].size

    def joined_text(self, page_width: float = 0.0) -> str:
        """
        Join spans into a string, inserting synthetic spaces when the
        horizontal gap between consecutive spans indicates a word boundary.

        Also inserts a tab-like gap marker "  " (two spaces) at detected
        column breaks so callers can split on it if they need columns.
        """
        if not self.spans:
            return ""

        result = self.spans[0].text
        for i in range(1, len(self.spans)):
            prev = self.spans[i - 1]
            curr = self.spans[i]

            gap = curr.x0 - prev.x1
            avg_char_w = max(1.0, curr.size * 0.5)

            if gap >= COLUMN_GAP_FACTOR * avg_char_w:
                # Large gap — column separator; use a double space so callers
                # can recognise it as a potential column boundary.
                result += "  " + curr.text
            elif gap >= GAP_SPACE_THRESHOLD * avg_char_w:
                # Normal word gap — add a single space if not already there.
                if not result.endswith(" ") and not curr.text.startswith(" "):
                    result += " "
                result += curr.text
            else:
                # Spans touch or slightly overlap (ligatures, Type3 per-glyph
                # fonts) — concatenate directly without adding a space, unless
                # the text already starts/ends with one.
                if result.endswith(" ") or curr.text.startswith(" "):
                    result += curr.text
                else:
                    result += curr.text

        return result.strip()


@dataclass
class TextParagraph:
    """One or more lines that flow together as a single logical paragraph."""
    lines: list[TextLine]
    is_table_row: bool = False   # hint for the DOCX writer

    @property
    def text(self) -> str:
        return " ".join(l.joined_text() for l in self.lines).strip()

    @property
    def x0(self) -> float:
        return min((l.x0 for l in self.lines), default=0.0)

    @property
    def dominant_size(self) -> float:
        sizes = [l.dominant_size for l in self.lines]
        return sum(sizes) / len(sizes) if sizes else 10.0

    @property
    def bold(self) -> bool:
        """True if the majority of non-whitespace characters are bold."""
        bold_chars = sum(
            len(s.text.strip()) for l in self.lines
            for s in l.spans if s.bold
        )
        total_chars = sum(
            len(s.text.strip()) for l in self.lines for s in l.spans
        )
        return total_chars > 0 and bold_chars / total_chars >= 0.5


@dataclass
class TableCell:
    text: str
    bold: bool = False


@dataclass
class Table:
    """A detected grid structure with row/column alignment."""
    rows: list[list[TableCell]]
    x0: float = 0.0
    y0: float = 0.0


@dataclass
class EmbeddedImage:
    """Raster or vector image extracted from the page."""
    xref: int        # fitz image xref
    bbox: tuple[float, float, float, float]  # x0 y0 x1 y1 in page coordinates
    data: bytes = field(repr=False, default=b"")
    ext: str = "png"


@dataclass
class PageContent:
    """Everything extracted from one PDF page, ready for DOCX writing."""
    page_num: int
    width: float
    height: float
    paragraphs: list[TextParagraph]
    tables: list[Table]
    images: list[EmbeddedImage]


# --------------------------------------------------------------------------- #
# Span extraction (Bug 3 + Bug 4 fix)                                         #
# --------------------------------------------------------------------------- #

def _flags_to_style(flags: int, font_name: str = "") -> tuple[bool, bool]:
    """
    Decode PyMuPDF span flags + font name → (bold, italic).

    The flags bitmask (bit 4 = bold, bit 1 = italic) is the primary source.
    Many PDF generators (Word, LibreOffice, web renderers) export flags=0 for
    ALL spans and instead encode style in the font name — e.g. "Arial,Bold",
    "Helvetica-BoldOblique", "TimesNewRoman-Italic".  We check the font name
    as a fallback so those documents retain their formatting.
    """
    bold   = bool(flags & (1 << 4))
    italic = bool(flags & (1 << 1))
    if font_name and not (bold or italic):
        fn = font_name.upper()
        bold   = ("BOLD" in fn or fn.endswith(",BD") or "-BD" in fn
                  or fn.endswith("-B") or ",BOLD" in fn)
        italic = ("ITALIC" in fn or "OBLIQUE" in fn
                  or "-IT" in fn or "-OB" in fn or ",IT" in fn)
    return bold, italic


def _strip_pua(text: str) -> str:
    """
    Remove Unicode Private-Use-Area codepoints that PDFs use for icon/symbol
    fonts.  Word has no mapping for these glyphs and shows them as □ boxes.
    Ranges stripped: U+E000–U+F8FF (BMP PUA) and U+F0000–U+10FFFF (sup PUA).
    """
    return "".join(
        ch for ch in text
        if not (0xE000 <= ord(ch) <= 0xF8FF or ord(ch) >= 0xF0000)
    )


def _extract_raw_spans(page: fitz.Page) -> list[TextSpan]:
    """
    Extract all text spans from the page WITHOUT suppressing any by image
    positions (Bug 3 fix).  Also walks annotations and widgets (Bug 4 fix).

    Space glyphs (text == ' ', '  ', etc.) are preserved — NOT dropped.
    Dropping them and relying on gap detection alone fails when two words are
    positioned such that their residual gap is below the threshold (e.g.
    tight kerning, or when the space glyph exactly fills the visual gap).
    Keeping them means the original PDF's word boundaries survive faithfully.
    """
    spans: list[TextSpan] = []

    # ── 1. Main text content via get_text("dict") ────────────────────────────
    # flags=TEXT_PRESERVE_WHITESPACE keeps explicit space glyphs intact.
    raw = page.get_text(
        "dict",
        flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES,
    )
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            # Image block — skip, handled separately below.
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text:          # skip only truly empty strings
                    continue
                # Skip zero-width whitespace (decorative glyphs with no extent)
                bbox = span.get("bbox", (0, 0, 0, 0))
                if not text.strip() and bbox[2] - bbox[0] < 0.1:
                    continue
                # Strip Private-Use-Area codepoints (U+E000–U+F8FF, U+F0000+).
                # These are icon/symbol glyphs from custom PDF fonts that Word
                # cannot render — they appear as □ boxes in the output.
                text = _strip_pua(text)
                if not text:
                    continue
                bold, italic = _flags_to_style(
                    span.get("flags", 0),
                    span.get("font", ""),
                )
                spans.append(TextSpan(
                    text=text,
                    x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3],
                    size=float(span.get("size", 10)),
                    bold=bold,
                    italic=italic,
                    color=int(span.get("color", 0)),
                ))

    # ── 2. Annotation text (Bug 4 fix) ───────────────────────────────────────
    for annot in page.annots():
        info = annot.info or {}
        text = (info.get("content") or info.get("subject") or "").strip()
        if not text:
            continue
        r = annot.rect
        spans.append(TextSpan(
            text=text,
            x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1,
            size=10.0, bold=False, italic=False, color=0,
        ))

    # ── 3. Form widget values (Bug 4 fix) ────────────────────────────────────
    try:
        for widget in (page.widgets() or []):
            val = str(widget.field_value or "").strip()
            if not val:
                continue
            r = widget.rect
            spans.append(TextSpan(
                text=val,
                x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1,
                size=10.0, bold=False, italic=False, color=0,
            ))
    except Exception:
        pass

    return spans


# --------------------------------------------------------------------------- #
# Span → line grouping (Bug 2 fix)                                            #
# --------------------------------------------------------------------------- #

def _cluster_into_lines(spans: list[TextSpan]) -> list[TextLine]:
    """
    Group spans into visual lines by baseline proximity (Bug 2 fix).

    Algorithm:
      1. Compute y-centre for each span.
      2. Sort spans by y-centre.
      3. Greedily assign each span to the current line if its y-centre is
         within BASELINE_TOLERANCE_FACTOR * median_height of the line's
         running y-centre; otherwise start a new line.
      4. Within each line, sort spans by x0 (left-to-right reading order).
    """
    if not spans:
        return []

    heights = [s.y1 - s.y0 for s in spans if s.y1 > s.y0]
    median_h = sorted(heights)[len(heights) // 2] if heights else 10.0
    tolerance = BASELINE_TOLERANCE_FACTOR * max(median_h, 1.0)

    # Sort all spans top-to-bottom (by y-centre)
    sorted_spans = sorted(spans, key=lambda s: (s.y0 + s.y1) / 2)

    lines: list[list[TextSpan]] = []
    current_group: list[TextSpan] = [sorted_spans[0]]
    current_y = (sorted_spans[0].y0 + sorted_spans[0].y1) / 2

    for span in sorted_spans[1:]:
        span_y = (span.y0 + span.y1) / 2
        if abs(span_y - current_y) <= tolerance:
            current_group.append(span)
            # Update running y-centre (mean of group)
            current_y = sum((s.y0 + s.y1) / 2 for s in current_group) / len(current_group)
        else:
            lines.append(sorted(current_group, key=lambda s: s.x0))
            current_group = [span]
            current_y = span_y

    lines.append(sorted(current_group, key=lambda s: s.x0))

    return [TextLine(spans=grp) for grp in lines if grp]


# --------------------------------------------------------------------------- #
# Line → paragraph grouping                                                   #
# --------------------------------------------------------------------------- #

def _group_lines_into_paragraphs(lines: list[TextLine]) -> list[TextParagraph]:
    """
    Group consecutive lines into paragraphs by vertical gap analysis.
    A gap > 1.5 × median positive inter-line gap = paragraph break.
    """
    if not lines:
        return []

    if len(lines) == 1:
        return [TextParagraph(lines=lines)]

    y_centers = [l.y_center for l in lines]
    gaps = [
        max(0.0, y_centers[i] - y_centers[i - 1])
        for i in range(1, len(y_centers))
    ]

    positive_gaps = [g for g in gaps if g > 0]
    if positive_gaps:
        median_gap = sorted(positive_gaps)[len(positive_gaps) // 2]
        threshold = max(1.0, 1.5 * median_gap)
    else:
        threshold = float("inf")

    paragraphs: list[TextParagraph] = []
    current: list[TextLine] = [lines[0]]

    for i in range(1, len(lines)):
        gap = max(0.0, y_centers[i] - y_centers[i - 1])
        if gap > threshold:
            paragraphs.append(TextParagraph(lines=current))
            current = [lines[i]]
        else:
            current.append(lines[i])

    paragraphs.append(TextParagraph(lines=current))
    return paragraphs


# --------------------------------------------------------------------------- #
# Table detection                                                              #
# --------------------------------------------------------------------------- #

def _detect_tables(
    paragraphs: list[TextParagraph],
) -> tuple[list[TextParagraph], list[Table]]:
    """
    Scan paragraphs for table-like structures: >= TABLE_MIN_ROWS consecutive
    single-line paragraphs where spans cluster into >= TABLE_MIN_COLS
    x-aligned columns.

    Returns (remaining_paragraphs, detected_tables) where table paragraphs
    are removed from remaining_paragraphs.
    """
    tables: list[Table] = []
    remaining: list[TextParagraph] = []
    i = 0

    while i < len(paragraphs):
        # Multi-line paragraph → definitely not a table row; skip it.
        if len(paragraphs[i].lines) != 1:
            remaining.append(paragraphs[i])
            i += 1
            continue

        # Collect a run of consecutive single-line paragraphs.
        candidate_rows: list[TextParagraph] = []
        while i < len(paragraphs) and len(paragraphs[i].lines) == 1:
            candidate_rows.append(paragraphs[i])
            i += 1

        if len(candidate_rows) < TABLE_MIN_ROWS:
            remaining.extend(candidate_rows)
            continue

        # Check column alignment: collect x0 of first span on each line
        # and x0 of subsequent column-gap spans
        row_col_xs: list[list[float]] = []
        for para in candidate_rows:
            line = para.lines[0]
            # Find column-gap splits in the line
            col_xs = [line.x0]
            avg_char_w = max(1.0, line.dominant_size * 0.5)
            for j in range(1, len(line.spans)):
                gap = line.spans[j].x0 - line.spans[j - 1].x1
                if gap >= COLUMN_GAP_FACTOR * avg_char_w:
                    col_xs.append(line.spans[j].x0)
            row_col_xs.append(col_xs)

        # Only rows with >= TABLE_MIN_COLS columns participate
        valid_rows = [r for r, xs in zip(candidate_rows, row_col_xs)
                      if len(xs) >= TABLE_MIN_COLS]
        valid_xs   = [xs for xs in row_col_xs if len(xs) >= TABLE_MIN_COLS]

        if len(valid_rows) < TABLE_MIN_ROWS:
            remaining.extend(candidate_rows)
            continue

        # Check that column x-positions cluster (at least the first 2 columns)
        first_col_xs  = [xs[0] for xs in valid_xs]
        second_col_xs = [xs[1] for xs in valid_xs]
        first_spread  = max(first_col_xs) - min(first_col_xs)
        second_spread = max(second_col_xs) - min(second_col_xs)

        if first_spread > TABLE_COL_TOL or second_spread > TABLE_COL_TOL:
            remaining.extend(candidate_rows)
            continue

        # We have a table.  Build rows.
        table_rows: list[list[TableCell]] = []
        for para in valid_rows:
            line = para.lines[0]
            # Split into columns at large gaps
            avg_char_w = max(1.0, line.dominant_size * 0.5)
            cells: list[list[TextSpan]] = [[]]
            for j, span in enumerate(line.spans):
                if j > 0:
                    gap = span.x0 - line.spans[j - 1].x1
                    if gap >= COLUMN_GAP_FACTOR * avg_char_w:
                        cells.append([])
                cells[-1].append(span)
            table_rows.append([
                TableCell(
                    text=" ".join(s.text.strip() for s in cell_spans if s.text.strip()),
                    bold=any(s.bold for s in cell_spans),
                )
                for cell_spans in cells if cell_spans
            ])

        # Add non-table rows from the candidate run to remaining
        valid_set = set(id(p) for p in valid_rows)
        for para in candidate_rows:
            if id(para) not in valid_set:
                remaining.append(para)

        x0 = min(p.x0 for p in valid_rows)
        y0 = valid_rows[0].lines[0].spans[0].y0 if valid_rows else 0.0
        tables.append(Table(rows=table_rows, x0=x0, y0=y0))

    return remaining, tables


# --------------------------------------------------------------------------- #
# Image extraction                                                             #
# --------------------------------------------------------------------------- #

def _extract_images(page: fitz.Page) -> list[EmbeddedImage]:
    """Extract raster images embedded in the page with their positions."""
    images: list[EmbeddedImage] = []
    page_h = page.rect.height

    for item in page.get_images(full=True):
        xref = item[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            if rect.width < 20 or rect.height < 20:
                continue  # skip tiny decorative images
            try:
                img_info = page.parent.extract_image(xref)
                data = img_info.get("image", b"")
                ext  = img_info.get("ext", "png")
            except Exception:
                data, ext = b"", "png"
            images.append(EmbeddedImage(
                xref=xref,
                bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                data=data,
                ext=ext,
            ))

    return images


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def extract_page(page: fitz.Page, page_num: int = 0) -> PageContent:
    """
    Extract all text, tables, and images from a fitz.Page, applying all
    four bug-class fixes described in the module docstring.

    Returns a PageContent whose paragraphs are in human reading order
    (top-to-bottom; within each line, left-to-right).
    """
    raw_spans = _extract_raw_spans(page)

    if not raw_spans:
        return PageContent(
            page_num=page_num,
            width=page.rect.width,
            height=page.rect.height,
            paragraphs=[],
            tables=[],
            images=_extract_images(page),
        )

    lines      = _cluster_into_lines(raw_spans)
    paragraphs = _group_lines_into_paragraphs(lines)

    # Sort paragraphs top-to-bottom (y of first line's first span)
    paragraphs.sort(key=lambda p: p.lines[0].y_center if p.lines else 0.0)

    remaining_paras, tables = _detect_tables(paragraphs)

    logger.debug(
        "Page %d: %d spans → %d lines → %d paragraphs → %d tables, %d images",
        page_num,
        len(raw_spans),
        len(lines),
        len(remaining_paras),
        len(tables),
        0,  # images counted separately
    )

    return PageContent(
        page_num=page_num,
        width=page.rect.width,
        height=page.rect.height,
        paragraphs=remaining_paras,
        tables=tables,
        images=_extract_images(page),
    )


def extract_document(doc: fitz.Document) -> list[PageContent]:
    """Extract all pages of an open fitz.Document."""
    return [extract_page(doc[i], i) for i in range(doc.page_count)]
