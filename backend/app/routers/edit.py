import base64
import json
import uuid
from collections import defaultdict
from pathlib import Path

import fitz
from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from starlette.background import BackgroundTask

from app.config import settings
from app.errors import ConversionError
from app.utils.tempdir import cleanup_dir, scratch_dir
from app.utils.validation import check_extension, check_size, get_extension

router = APIRouter()

MAX_ELEMENTS = 200
MAX_REPLACEMENTS = 500
MAX_TEXT_LENGTH = 2000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Cap on font bytes re-embedded per replacement; larger fonts are skipped and
# the Base14 fallback is used instead.
MAX_FONT_BYTES = 4 * 1024 * 1024
PDF_EXTENSIONS = frozenset({".pdf"})

# Font types that PyMuPDF's insert_text(fontbuffer=) can handle.
# CIDFont / Type0 (common in CJK PDFs) and Type3 (bitmap) are excluded.
_EMBEDDABLE_FONT_TYPES = frozenset({"Type1", "TrueType", "OpenType", "CFF", "Type1C"})

# Maps (family, bold, italic) → PyMuPDF Base14 font shortname.
# Used as a fallback when the original embedded font cannot be re-used.
_FONT_MAP: dict[tuple[str, bool, bool], str] = {
    ("helvetica", False, False): "helv",
    ("helvetica", True,  False): "hebo",
    ("helvetica", False, True):  "heit",
    ("helvetica", True,  True):  "hebi",
    ("times",     False, False): "tiro",
    ("times",     True,  False): "tibo",
    ("times",     False, True):  "tiit",
    ("times",     True,  True):  "tibi",
    ("courier",   False, False): "cour",
    ("courier",   True,  False): "cobo",
    ("courier",   False, True):  "coit",
    ("courier",   True,  True):  "cobi",
}
_VALID_FAMILIES = frozenset({"helvetica", "times", "courier"})


def _resolve_fontname(family: str | None, bold: bool, italic: bool) -> str:
    f = (family or "helvetica").lower()
    if f not in _VALID_FAMILIES:
        f = "helvetica"
    return _FONT_MAP[(f, bold, italic)]


class TextReplacement(BaseModel):
    """Redact an existing text span and reinsert new text with matching style."""
    page: int        # 0-indexed
    x0: float        # PDF points — y-up (bottom-left) coordinate system
    y0: float
    x1: float
    y1: float
    new_text: str
    # Exact PDF-space (y-up) baseline Y sent by the frontend.
    # When present, insert_text() is used for pixel-accurate placement.
    # When absent (old clients), insert_textbox() with a padded rect is the fallback.
    baseline_y: float | None = None


# PDF font name fragments → Base14 family for the fallback path.
_FAMILY_HINTS: list[tuple[str, str]] = [
    ("helvetica", "helvetica"),
    ("arial",     "helvetica"),
    ("calibri",   "helvetica"),
    ("myriad",    "helvetica"),
    ("gill",      "helvetica"),
    ("futura",    "helvetica"),
    ("times",     "times"),
    ("georgia",   "times"),
    ("garamond",  "times"),
    ("palatino",  "times"),
    ("bookman",   "times"),
    ("courier",   "courier"),
    ("consolas",  "courier"),
    ("monaco",    "courier"),
    ("mono",      "courier"),
    ("code",      "courier"),
]


def _guess_font_family(raw_font: str) -> str:
    name = raw_font.lower()
    if "+" in name:
        name = name.split("+", 1)[1]
    for hint, family in _FAMILY_HINTS:
        if hint in name:
            return family
    return "helvetica"


def _detect_span_style(page: fitz.Page, rect: fitz.Rect) -> tuple[dict, str | None]:
    """
    Return (style, pdf_font_name) for the dominant text span in rect.

    style: {fontname: Base14 fallback, fontsize: float, color: int (packed 0xRRGGBB)}
    pdf_font_name: raw PDF font name such as "ABCDEF+HelveticaNeue-Bold", used
                   downstream to locate the original embedded font for re-use.
    """
    search_rect = rect + fitz.Rect(-1, -1, 1, 1)
    blocks = page.get_text("dict", clip=search_rect).get("blocks", [])

    best: dict = {}
    best_area = 0.0
    best_pdf_font: str | None = None

    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                sr = fitz.Rect(span["bbox"])
                inter = sr & search_rect
                area = inter.get_area() if not inter.is_empty else 0.0
                if area > best_area:
                    best_area = area
                    family = _guess_font_family(span.get("font", ""))
                    raw_flags = span.get("flags", 0)
                    bold   = bool(raw_flags & 16)
                    italic = bool(raw_flags & 2)
                    best = {
                        "fontname": _resolve_fontname(family, bold, italic),
                        "fontsize": max(4.0, min(span.get("size", 12.0), 144.0)),
                        "color":    span.get("color", 0),
                    }
                    best_pdf_font = span.get("font")

    if not best:
        best = {"fontname": "helv", "fontsize": 12.0, "color": 0}
    return best, best_pdf_font


def _find_font_xref(page: fitz.Page, pdf_font_name: str) -> int:
    """
    Return the PDF xref of the font whose name matches pdf_font_name.
    Handles subset prefixes ("ABCDEF+FontName") and plain names.
    Returns 0 if not found.
    """
    base_name = pdf_font_name.split("+", 1)[-1] if "+" in pdf_font_name else pdf_font_name
    try:
        for xref, _ext, _ftype, basename, name, _enc, _ref in page.get_fonts(full=True):
            if name == pdf_font_name or basename == base_name or name == base_name:
                return xref
    except Exception:
        pass
    return 0


def _try_extract_font(doc: fitz.Document, xref: int) -> bytes | None:
    """
    Extract the embedded font bytes for a given xref.

    Returns None when:
    - The font is not embedded (only a name reference, e.g. a standard system font).
    - The font type is not supported by insert_text() (CIDFont/Type0, Type3).
    - The font data exceeds MAX_FONT_BYTES.
    """
    if not xref:
        return None
    try:
        _name, _ext, ftype, _encoding, content = doc.extract_font(xref)
        if not content or len(content) > MAX_FONT_BYTES:
            return None
        if ftype in _EMBEDDABLE_FONT_TYPES:
            return bytes(content)
    except Exception:
        pass
    return None


def _sample_bg_color(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """
    Sample the page background color adjacent to rect.

    Renders a thin strip immediately above (or below, if at the top of the page)
    the redaction rect at 2× resolution and reads the centre pixel.  This lets
    the redaction fill blend with coloured backgrounds or headers rather than
    always leaving a white rectangle.
    """
    # In fitz y-down: y0 is the TOP, y1 the BOTTOM of the rect.
    if rect.y0 >= 4:
        strip = fitz.Rect(rect.x0, rect.y0 - 4, min(rect.x0 + 12, rect.x1), rect.y0)
    elif rect.y1 + 4 <= page.rect.height:
        strip = fitz.Rect(rect.x0, rect.y1, min(rect.x0 + 12, rect.x1), rect.y1 + 4)
    else:
        return (1.0, 1.0, 1.0)

    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=strip, colorspace=fitz.csRGB)
        if pix.n >= 3 and pix.width > 0 and pix.height > 0:
            r, g, b = pix.pixel(pix.width // 2, pix.height // 2)[:3]
            return (r / 255.0, g / 255.0, b / 255.0)
    except Exception:
        pass
    return (1.0, 1.0, 1.0)


def _packed_color_to_rgb(packed: int) -> tuple[float, float, float]:
    r = ((packed >> 16) & 0xFF) / 255
    g = ((packed >> 8)  & 0xFF) / 255
    b = (packed         & 0xFF) / 255
    return (r, g, b)


class EditElement(BaseModel):
    page: int
    type: str
    x: float
    y: float
    width: float
    height: float
    text: str | None = None
    fontSize: float | None = None
    fontFamily: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    image: str | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _hex_to_rgb(color: str | None) -> tuple[float, float, float]:
    if not color:
        return (0.0, 0.0, 0.0)
    color = color.lstrip("#")
    if len(color) != 6:
        return (0.0, 0.0, 0.0)
    try:
        return (
            int(color[0:2], 16) / 255,
            int(color[2:4], 16) / 255,
            int(color[4:6], 16) / 255,
        )
    except ValueError:
        return (0.0, 0.0, 0.0)


def _decode_image(data: str) -> bytes:
    if data.strip().startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data)
    except Exception as exc:
        raise ConversionError(
            400, "invalid_image", "Could not decode a stamp/signature image."
        ) from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise ConversionError(400, "invalid_image", "A stamp/signature image is too large.")
    return raw


@router.post("/api/edit")
async def edit_pdf(
    file: UploadFile,
    elements: str = Form(...),
    text_replacements: str = Form("[]"),
) -> FileResponse:
    extension = get_extension(file.filename)
    check_extension(extension, PDF_EXTENSIONS)

    try:
        raw_elements = json.loads(elements)
    except json.JSONDecodeError as exc:
        raise ConversionError(
            400, "invalid_elements", "Elements payload is not valid JSON."
        ) from exc
    if not isinstance(raw_elements, list):
        raise ConversionError(400, "invalid_elements", "Elements payload must be a list.")
    if len(raw_elements) > MAX_ELEMENTS:
        raise ConversionError(400, "invalid_elements", f"Too many elements (max {MAX_ELEMENTS}).")
    try:
        parsed = [EditElement.model_validate(e) for e in raw_elements]
    except ValidationError as exc:
        raise ConversionError(
            400, "invalid_elements", "One or more elements are malformed."
        ) from exc

    try:
        raw_replacements = json.loads(text_replacements)
    except json.JSONDecodeError as exc:
        raise ConversionError(
            400, "invalid_replacements", "text_replacements payload is not valid JSON."
        ) from exc
    if not isinstance(raw_replacements, list):
        raise ConversionError(400, "invalid_replacements", "text_replacements must be a list.")
    if len(raw_replacements) > MAX_REPLACEMENTS:
        raise ConversionError(
            400, "invalid_replacements", f"Too many replacements (max {MAX_REPLACEMENTS})."
        )
    try:
        parsed_replacements = [TextReplacement.model_validate(r) for r in raw_replacements]
    except ValidationError as exc:
        raise ConversionError(
            400, "invalid_replacements", "One or more replacements are malformed."
        ) from exc

    with scratch_dir() as tmp_dir:
        try:
            input_path = tmp_dir / f"{uuid.uuid4().hex}.pdf"
            size = 0
            max_bytes = settings.max_upload_bytes
            with open(input_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        break
                    f.write(chunk)
            check_size(size, max_bytes)

            try:
                doc = fitz.open(input_path)
            except Exception as exc:
                raise ConversionError(
                    422, "unreadable_file", "The PDF could not be read. It may be corrupted."
                ) from exc

            try:
                if not doc.is_pdf or doc.page_count == 0:
                    raise ConversionError(
                        422, "unreadable_file", "The uploaded file is not a valid PDF."
                    )

                # ── Phase 1: in-place text replacements ──────────────────────────
                #
                # Strategy per page:
                # 1. Detect original font/size/color for each span.  Attempt to
                #    extract the embedded font bytes so the replacement text uses
                #    the same typeface, not a Base14 substitute.
                # 2. Sample the page background colour near each span so the
                #    redaction rectangle blends in on non-white pages.
                # 3. Apply all redactions in one pass (apply_redactions is O(page)).
                # 4. Reinsert with insert_text() at the exact baseline when the
                #    client provided baseline_y, falling back to insert_textbox()
                #    with a padded rect for older clients or on insertion errors.
                replacements_by_page: dict[int, list[TextReplacement]] = defaultdict(list)
                for rep in parsed_replacements:
                    if 0 <= rep.page < doc.page_count:
                        replacements_by_page[rep.page].append(rep)

                for page_idx, reps in replacements_by_page.items():
                    page = doc[page_idx]
                    ph = page.rect.height

                    # Collect metadata BEFORE any redaction (page state changes after).
                    styles:       list[dict]          = []
                    bg_colors:    list[tuple]         = []
                    font_buffers: list[bytes | None]  = []

                    for rep in reps:
                        rect = fitz.Rect(rep.x0, ph - rep.y1, rep.x1, ph - rep.y0)
                        style, pdf_font_name = _detect_span_style(page, rect)
                        styles.append(style)
                        bg_colors.append(_sample_bg_color(page, rect))

                        font_buf: bytes | None = None
                        if pdf_font_name:
                            xref = _find_font_xref(page, pdf_font_name)
                            font_buf = _try_extract_font(doc, xref)
                        font_buffers.append(font_buf)

                    # Stamp redaction annotations using the sampled background colour.
                    for rep, bg in zip(reps, bg_colors):
                        rect = fitz.Rect(rep.x0, ph - rep.y1, rep.x1, ph - rep.y0)
                        page.add_redact_annot(rect, fill=bg)

                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                    # Reinsert new text for each replacement.
                    for i, (rep, style, font_buf) in enumerate(zip(reps, styles, font_buffers)):
                        fs    = style["fontsize"]
                        color = _packed_color_to_rgb(style["color"])
                        text  = rep.new_text[:MAX_TEXT_LENGTH]

                        if rep.baseline_y is not None:
                            # Precise path: place text at the exact original baseline.
                            # Each embedded font gets a unique resource name within
                            # the page so different fonts on the same page don't collide.
                            baseline_fitz_y = ph - rep.baseline_y
                            insert_kwargs: dict = {
                                "fontsize":    fs,
                                "color":       color,
                                "render_mode": 0,
                            }
                            if font_buf:
                                insert_kwargs["fontbuffer"] = font_buf
                                insert_kwargs["fontname"]   = f"eF{i}"
                            else:
                                insert_kwargs["fontname"] = style["fontname"]
                            try:
                                page.insert_text(
                                    fitz.Point(rep.x0, baseline_fitz_y),
                                    text,
                                    **insert_kwargs,
                                )
                                continue   # precise path succeeded
                            except Exception:
                                pass       # fall through to textbox fallback

                        # Fallback: insert_textbox with a vertically expanded rect.
                        # The extra padding prevents the text from silently overflowing
                        # and being dropped when insert_textbox's line-height check fails.
                        pad = max(fs * 0.25, 4.0)
                        top    = ph - rep.y1
                        bottom = ph - rep.y0
                        insert_rect = fitz.Rect(rep.x0, top - pad, rep.x1, bottom + pad)
                        page.insert_textbox(
                            insert_rect,
                            text,
                            fontsize=fs,
                            fontname=style["fontname"],
                            color=color,
                            render_mode=0,
                            align=fitz.TEXT_ALIGN_LEFT,
                        )

                # ── Phase 2: overlay elements (text boxes, stamps, signatures) ──
                for el in parsed:
                    if el.page < 0 or el.page >= doc.page_count:
                        continue
                    page = doc[el.page]
                    page_width  = page.rect.width
                    page_height = page.rect.height
                    x0 = _clamp01(el.x) * page_width
                    y0 = _clamp01(el.y) * page_height
                    x1 = x0 + _clamp01(el.width)  * page_width
                    y1 = y0 + _clamp01(el.height) * page_height
                    rect = fitz.Rect(x0, y0, x1, y1)

                    if el.type == "text" and el.text:
                        text = el.text[:MAX_TEXT_LENGTH]
                        font_size = min(max(el.fontSize or 12.0, 4.0), 144.0)
                        fontname  = _resolve_fontname(el.fontFamily, el.bold, el.italic)
                        page.insert_textbox(
                            rect, text,
                            fontsize=font_size,
                            fontname=fontname,
                            color=_hex_to_rgb(el.color),
                            render_mode=0,
                            underline=el.underline,
                        )

                    elif el.type == "image" and el.image:
                        image_bytes = _decode_image(el.image)
                        try:
                            page.insert_image(rect, stream=image_bytes)
                        except Exception as exc:
                            raise ConversionError(
                                422, "invalid_image",
                                "One of the stamp/signature images could not be placed.",
                            ) from exc

                output_path = tmp_dir / "edited.pdf"
                # garbage=4  removes all unreferenced objects (including orphaned fonts
                #             left after redaction); deflate/clean keep the file minimal.
                doc.save(output_path, garbage=4, deflate=True, clean=True)
            finally:
                doc.close()
        except Exception:
            cleanup_dir(tmp_dir)
            raise

        original_stem = Path(file.filename).stem if file.filename else "edited"
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"{original_stem}-edited.pdf",
            background=BackgroundTask(cleanup_dir, tmp_dir),
        )
