"""
Reuse Type3 PDF fonts when TrueType bytes are not extractable.

HTML-to-PDF tickets (Chrome) often embed the original family as many Type3
subsets. extract_font() returns no bytes, so the generic resolver falls through
to Helvetica and the edited text changes style. When every replacement
character already exists in a matching Type3 face, rewrite the original glyph
procedures instead of substituting a Base-14 font.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz


_TYPE3_XREF_RE = re.compile(r"Type3\s*\((\d+)\s+0\s+R\)", re.I)
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")


@dataclass(frozen=True)
class Type3FaceStyle:
    family: str
    face: str
    weight: int
    italic: bool
    resource: str
    xref: int
    flip_y: bool
    fd_xref: int = 0


@dataclass(frozen=True)
class Type3Glyph:
    resource: str
    code: int
    width_em: float
    flip_y: bool


@dataclass
class Type3Layout:
    glyphs: list[Type3Glyph]
    family: str
    face: str
    weight: int
    italic: bool

    def width(self, fontsize: float, scale: float = 1.0) -> float:
        return sum(g.width_em * fontsize * scale for g in self.glyphs)


@dataclass
class _Type3Font:
    xref: int
    resource: str
    family: str
    face: str
    weight: int
    italic: bool
    flip_y: bool
    fd_xref: int
    # unicode char → (code, width_em)
    glyphs: dict[str, tuple[int, float]] = field(default_factory=dict)


def type3_xref_from_name(font_name: str, page: fitz.Page | None = None) -> int | None:
    match = _TYPE3_XREF_RE.search(font_name or "")
    if match:
        return int(match.group(1))
    if not font_name or page is None:
        return None
    try:
        for entry in page.get_fonts(full=True):
            if str(entry[2]) != "Type3" or int(entry[0]) <= 0:
                continue
            if font_name in {str(entry[3]), str(entry[4]), f"Type3 ({entry[0]} 0 R)"}:
                return int(entry[0])
    except Exception:
        return None
    return None


def type3_face_style(
    doc: fitz.Document,
    font_name: str,
    page: fitz.Page | None = None,
) -> Type3FaceStyle | None:
    """Return family/weight for a PyMuPDF Type3 span font name."""
    xref = type3_xref_from_name(font_name, page)
    if xref is None:
        return None
    resource = ""
    if page is not None:
        try:
            for entry in page.get_fonts(full=True):
                if int(entry[0]) == xref:
                    resource = str(entry[4])
                    break
        except Exception:
            resource = ""
    parsed = _parse_type3_font(doc, xref, resource)
    if parsed is None:
        return None
    return Type3FaceStyle(
        family=parsed.family,
        face=parsed.face,
        weight=parsed.weight,
        italic=parsed.italic,
        resource=parsed.resource,
        xref=parsed.xref,
        flip_y=parsed.flip_y,
        fd_xref=parsed.fd_xref,
    )


def encode_with_type3(
    orig_doc: fitz.Document,
    orig_page: fitz.Page,
    dest_page: fitz.Page,
    source_font_name: str,
    text: str,
) -> Type3Layout | None:
    """
    Encode `text` with Type3 glyphs on dest_page that match the source face.

    Returns None when the source is not Type3 or a character cannot be encoded
    from a style-compatible Type3 font on the destination page.
    """
    if not text:
        return None
    if type3_xref_from_name(source_font_name, orig_page) is None:
        return None

    source = type3_face_style(orig_doc, source_font_name, orig_page)
    if source is None:
        return None

    dest_fonts = _load_page_type3_fonts(dest_page.parent, dest_page)
    if not dest_fonts:
        return None

    # Resource names can change after a page rebuild. Remap onto the dest
    # font that is the same face *and* the same weight. Chrome names every
    # Noto subset "NotoSans-Regular", so matching on face/name alone would
    # overwrite Bold with Regular and strip the original style.
    dest_match = next((font for font in dest_fonts if font.resource == source.resource), None)
    if dest_match is None and source.fd_xref:
        dest_match = next(
            (font for font in dest_fonts if font.fd_xref == source.fd_xref),
            None,
        )
    if dest_match is None:
        dest_match = next(
            (font for font in dest_fonts if _same_face(font, source)),
            None,
        )
    if dest_match is not None:
        source = Type3FaceStyle(
            family=dest_match.family or source.family,
            face=dest_match.face or source.face,
            weight=source.weight,
            italic=source.italic,
            resource=dest_match.resource,
            xref=dest_match.xref,
            flip_y=dest_match.flip_y,
            fd_xref=source.fd_xref or dest_match.fd_xref,
        )

    glyphs: list[Type3Glyph] = []
    for char in text:
        mapped = " " if char in {"\xa0", "\t"} else char
        if mapped == "\n":
            return None
        chosen = _pick_glyph(mapped, dest_fonts, source)
        if chosen is None:
            return None
        glyphs.append(chosen)

    return Type3Layout(
        glyphs=glyphs,
        family=source.family,
        face=source.face,
        weight=source.weight,
        italic=source.italic,
    )


def write_type3_text(
    page: fitz.Page,
    layout: Type3Layout,
    start_x: float,
    baseline_y: float,
    fontsize: float,
    color: tuple[float, float, float],
    right_to_left: bool = False,
) -> None:
    """Overlay Type3 glyphs in PyMuPDF user space (origin top-left, y-down)."""
    if not layout.glyphs:
        return
    r, g, b = color
    height = float(page.rect.height)
    parts = [
        "q",
        f"1 0 0 -1 0 {height:.6f} cm",
        f"{r:.6f} {g:.6f} {b:.6f} rg",
        "BT",
    ]
    x = start_x
    if right_to_left:
        x = start_x - layout.width(fontsize)
    last_resource: str | None = None
    for glyph in layout.glyphs:
        if glyph.resource != last_resource:
            parts.append(f"/{glyph.resource} {fontsize:.5f} Tf")
            last_resource = glyph.resource
        tm_y = -1 if glyph.flip_y else 1
        parts.append(f"1 0 0 {tm_y} {x:.4f} {baseline_y:.4f} Tm")
        parts.append(f"<{glyph.code:02X}> Tj")
        x += glyph.width_em * fontsize
    parts.extend(["ET", "Q"])
    _append_content_stream(page, "\n".join(parts).encode("ascii"))


def parse_tounicode(data: bytes) -> dict[int, str]:
    """Parse a ToUnicode CMap into byte-code → Unicode character."""
    text = data.decode("latin-1", errors="replace")
    mapping: dict[int, str] = {}
    for block in re.finditer(r"\d+\s+beginbfchar(.*?)endbfchar", text, re.S | re.I):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
            mapping[int(src, 16)] = _hex_to_char(dst)
    for block in re.finditer(r"\d+\s+beginbfrange(.*?)endbfrange", text, re.S | re.I):
        body = block.group(1)
        for src1, src2, dests in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[([^\]]+)\]",
            body,
        ):
            start = int(src1, 16)
            for i, dst in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", dests)):
                mapping[start + i] = _hex_to_char(dst)
        for src1, src2, dst in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            body,
        ):
            first, last, codepoint = int(src1, 16), int(src2, 16), int(dst, 16)
            for i, code in enumerate(range(first, last + 1)):
                mapping[code] = chr(codepoint + i)
    return {code: char for code, char in mapping.items() if char}


def _hex_to_char(dst: str) -> str:
    value = int(dst, 16)
    if value <= 0:
        return ""
    try:
        return chr(value)
    except ValueError:
        return ""


def _strip_subset_prefix(name: str) -> str:
    return _SUBSET_PREFIX_RE.sub("", name or "")


def _parse_pdf_numbers(array_text: str) -> list[float]:
    inner = array_text[array_text.find("[") + 1 : array_text.rfind("]")]
    return [float(token) for token in inner.split() if token not in {"[", "]"}]


def _parse_type3_font(doc: fitz.Document, xref: int, resource: str) -> _Type3Font | None:
    try:
        obj = doc.xref_object(xref) or ""
    except Exception:
        return None
    if "/Subtype /Type3" not in obj and "/Subtype/Type3" not in obj:
        return None

    family = ""
    face = ""
    weight = 400
    italic = False
    fd_xref = 0
    fd_match = re.search(r"/FontDescriptor\s+(\d+)\s+0\s+R", obj)
    if fd_match:
        fd_xref = int(fd_match.group(1))
        try:
            fd_obj = doc.xref_object(fd_xref) or ""
        except Exception:
            fd_obj = ""
        fam_match = re.search(r"/FontFamily\s*\(([^)]*)\)", fd_obj)
        name_match = re.search(r"/FontName\s*/([^\s/]+)", fd_obj)
        weight_match = re.search(r"/FontWeight\s+(\d+)", fd_obj)
        italic_match = re.search(r"/ItalicAngle\s+(-?\d+(?:\.\d+)?)", fd_obj)
        family = (fam_match.group(1) if fam_match else "").strip()
        face = _strip_subset_prefix(name_match.group(1) if name_match else "")
        if weight_match:
            weight = int(weight_match.group(1))
        if italic_match:
            italic = abs(float(italic_match.group(1))) > 0.1
        if not family and face:
            family = re.sub(r"[-_]?((Bold|Italic|Regular|Medium|Light|Condensed)+)$", "", face, flags=re.I)

    if not resource:
        resource = f"F{xref}"

    fm_match = re.search(r"/FontMatrix\s*(\[[^\]]*\])", obj)
    matrix = _parse_pdf_numbers(fm_match.group(1)) if fm_match else [0.001, 0, 0, 0.001, 0, 0]
    flip_y = len(matrix) >= 4 and matrix[3] < 0
    scale = abs(matrix[0]) if matrix else 0.001

    first = 0
    first_match = re.search(r"/FirstChar\s+(\d+)", obj)
    if first_match:
        first = int(first_match.group(1))
    widths_match = re.search(r"/Widths\s*(\[[^\]]*\])", obj, re.S)
    widths = _parse_pdf_numbers(widths_match.group(1)) if widths_match else []

    mapping: dict[int, str] = {}
    tu_match = re.search(r"/ToUnicode\s+(\d+)\s+0\s+R", obj)
    if tu_match:
        try:
            tu_stream = doc.xref_stream(int(tu_match.group(1)))
        except Exception:
            tu_stream = None
        if tu_stream:
            mapping = parse_tounicode(tu_stream)

    glyphs: dict[str, tuple[int, float]] = {}
    for code, char in mapping.items():
        idx = code - first
        width_units = widths[idx] if 0 <= idx < len(widths) else 0.0
        glyphs[char] = (code, width_units * scale)

    return _Type3Font(
        xref=xref,
        resource=resource,
        family=family or face,
        face=face or family,
        weight=weight,
        italic=italic,
        flip_y=flip_y,
        fd_xref=fd_xref,
        glyphs=glyphs,
    )


def _load_page_type3_fonts(doc: fitz.Document, page: fitz.Page) -> list[_Type3Font]:
    fonts: list[_Type3Font] = []
    try:
        entries = page.get_fonts(full=True)
    except Exception:
        return fonts
    for entry in entries:
        xref, ftype, resource = int(entry[0]), str(entry[2]), str(entry[4])
        if ftype != "Type3" or xref <= 0:
            continue
        parsed = _parse_type3_font(doc, xref, resource)
        if parsed is not None and parsed.glyphs:
            fonts.append(parsed)
    return fonts


def _weight_band(weight: int) -> str:
    """Group CSS/PDF weights so Regular is never mixed with Bold."""
    if weight >= 650:
        return "bold"
    if weight >= 500:
        return "medium"
    return "regular"


def _same_face(font: _Type3Font, source: Type3FaceStyle) -> bool:
    if source.family and font.family:
        if font.family.lower() != source.family.lower():
            return False
    elif source.face and font.face and font.face != source.face:
        return False
    if font.italic != source.italic:
        return False
    return _weight_band(font.weight) == _weight_band(source.weight)


def _pick_glyph(
    char: str,
    fonts: list[_Type3Font],
    source: Type3FaceStyle,
) -> Type3Glyph | None:
    # Chrome HTML-to-PDF names every Noto Sans subset "NotoSans-Regular"
    # even when FontWeight is 700. Never borrow a lighter/heavier subset
    # just because it happens to contain the missing letter.
    ranked = sorted(
        (font for font in fonts if _same_face(font, source)),
        key=lambda font: _face_rank(font, source),
    )
    for font in ranked:
        glyph = font.glyphs.get(char)
        if glyph is None:
            continue
        code, width_em = glyph
        return Type3Glyph(
            resource=font.resource,
            code=code,
            width_em=width_em,
            flip_y=font.flip_y,
        )
    return None


def _face_rank(font: _Type3Font, source: Type3FaceStyle) -> tuple[int, int, int]:
    """Lower is better: original subset, then same descriptor, then closer weight."""
    same_resource = int(font.resource != source.resource)
    same_fd = int(source.fd_xref != 0 and font.fd_xref != source.fd_xref)
    weight_delta = abs(font.weight - source.weight)
    return (same_resource, same_fd, weight_delta)


def snapshot_type3_resources(page: fitz.Page, resource_names: set[str]) -> dict[str, int]:
    """Record Type3 resource name → xref so fonts can be restored after redaction."""
    found: dict[str, int] = {}
    try:
        for entry in page.get_fonts(full=True):
            name = str(entry[4])
            if name in resource_names and str(entry[2]) == "Type3" and int(entry[0]) > 0:
                found[name] = int(entry[0])
    except Exception:
        return found
    return found


def restore_type3_resources(page: fitz.Page, resource_xrefs: dict[str, int]) -> None:
    """Re-attach Type3 fonts that redaction dropped from the page resource dict."""
    if not resource_xrefs:
        return
    try:
        present = {str(entry[4]) for entry in page.get_fonts(full=True)}
    except Exception:
        present = set()
    for name, xref in resource_xrefs.items():
        if not name or not xref or name in present:
            continue
        try:
            page.parent.xref_set_key(page.xref, f"Resources/Font/{name}", f"{xref} 0 R")
        except Exception:
            continue


def _append_content_stream(page: fitz.Page, extra: bytes) -> None:
    fitz.TOOLS._insert_contents(page, extra, True)
