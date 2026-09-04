"""
Font resolution for Phase 3 text edits.

Tier A  Reuse bytes from an embedded PDF font (with per-glyph coverage check),
        or a same-family system font when the embedded subset is incomplete.
        Type3 fonts are handled separately in type3_fonts (no extractable bytes).
Tier B  Family-matched Base-14 font (Helvetica / Times / Courier).
Tier C  Ubuntu OFL fonts from pymupdf-fonts (broad Latin/Greek/Cyrillic coverage).

If no tier has glyph coverage for every character in new_text, raise ValueError
with a message naming the failing codepoints. This is a hard block — never emit
tofu or corrupt glyphs.
"""
from __future__ import annotations

import os
import platform
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz
import pymupdf_fonts
from app.text_span_utils import infer_font_style


@dataclass
class FontResolution:
    tier: Literal["A", "B", "C"]
    fontname: str                              # fitz built-in name or registered name
    fontbuffer: bytes | None = field(default=None, repr=False)
    css_family: str = ""                       # reserved for future htmlbox use


@dataclass(frozen=True)
class SourceFace:
    """Original PDF face for any edited span — Type3, TrueType, or Base-14."""
    family: str
    face: str
    weight: int
    italic: bool

    @property
    def bold(self) -> bool:
        return self.weight >= 600


def css_weight(weight: int) -> int:
    """Snap a PDF/CSS weight to the 100–900 axis without collapsing 500/600 to 400/700."""
    snapped = int(round((weight or 400) / 100) * 100)
    return max(100, min(900, snapped))


# ── Base-14 helpers ───────────────────────────────────────────────────────────

def _base14_name(family_hint: str, bold: bool, italic: bool) -> str:
    """Map a family hint + style to a PyMuPDF Base-14 name."""
    f = family_hint.lower()
    if any(x in f for x in ("tir", "time", "roman", "serif", "georgia", "garamond")):
        if bold and italic: return "tibo"
        if bold: return "tib"
        if italic: return "tiit"
        return "tiro"
    if any(x in f for x in ("cour", "mono", "consol", "typewriter", "letter")):
        if bold and italic: return "cobi"
        if bold: return "cob"
        if italic: return "coit"
        return "cour"
    # Default: Helvetica / sans-serif
    if bold and italic: return "helbi"
    if bold: return "hebo"
    if italic: return "heit"
    return "helv"


def _ubuntu_fontname(bold: bool, italic: bool) -> str:
    if bold and italic: return "ubuntubi"
    if bold: return "ubuntubo"
    if italic: return "ubuntuit"
    return "ubuntu"


def _firago_fontname(bold: bool, italic: bool) -> str:
    """FiraGO provides broad Latin, Cyrillic, Greek, Arabic and Hebrew coverage."""
    if bold and italic: return "figbi"
    if bold: return "figbo"
    if italic: return "figit"
    return "figo"


def _guess_family(font_name: str) -> str:
    """Heuristically guess font family from an embedded font name."""
    n = (font_name or "").lower()
    if any(x in n for x in ("times", "roman", "georgia", "palatino", "garamond", "book")):
        return "serif"
    if any(x in n for x in ("courier", "console", "mono", "typewriter", "letter")):
        return "mono"
    return "sans"


# ── Glyph-coverage checks ─────────────────────────────────────────────────────

def _all_glyphs_present(font: fitz.Font, text: str) -> bool:
    return all(font.has_glyph(ord(c)) for c in text if not c.isspace())


def _missing_glyphs(font: fitz.Font, text: str) -> list[str]:
    return [c for c in text if not c.isspace() and not font.has_glyph(ord(c))]


def _all_glyphs_shapable(font: fitz.Font, text: str) -> bool:
    """Account for subset fonts that expose contextual presentation glyphs."""
    normalized_coverage = {
        char
        for codepoint in font.valid_codepoints()
        for char in unicodedata.normalize("NFKC", chr(codepoint))
    }
    return all(char in normalized_coverage for char in text if not char.isspace())


# ── Tier A: extract embedded font bytes ──────────────────────────────────────

def _strip_subset_prefix(name: str) -> str:
    """Remove 'ABCDEF+' subset prefix from a PDF font name."""
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def _font_key(name: str) -> str:
    """Normalize harmless PDF font-name punctuation and subset prefixes."""
    return re.sub(r"[^a-z0-9]", "", _strip_subset_prefix(name).lower())


_TYPE3_XREF_RE = re.compile(r"Type3\s*\((\d+)\s+0\s+R\)", re.I)


def _try_tier_a(
    doc: fitz.Document,
    page: fitz.Page,
    embedded_font_name: str,
    bold: bool,
    italic: bool,
    new_text: str,
) -> FontResolution | None:
    """
    Try to reuse the embedded font.  Returns FontResolution if usable, else None.
    """
    clean_target = _font_key(embedded_font_name)
    if not clean_target:
        return None

    try:
        for font_entry in page.get_fonts(full=True):
            xref = font_entry[0]
            basefont = font_entry[3]            # 4th element
            if xref == 0:
                continue
            clean_bf = _font_key(basefont)
            if clean_bf != clean_target:
                continue

            font_tuple = doc.extract_font(xref)  # (basefont, ext, type, buffer)
            font_bytes: bytes | None = font_tuple[3] if font_tuple else None
            if not font_bytes:
                continue

            try:
                font = fitz.Font(fontbuffer=font_bytes)
            except Exception:
                continue

            if not (
                _all_glyphs_present(font, new_text)
                or _all_glyphs_shapable(font, new_text)
            ):
                # The same font can occur in several embedded subsets. A later
                # subset may contain glyphs absent from this one.
                continue

            safe_name = re.sub(r"[^A-Za-z0-9]", "_", _strip_subset_prefix(basefont)) or "EmbFont"
            return FontResolution(
                tier="A",
                fontname=safe_name,
                fontbuffer=font_bytes,
                css_family=safe_name,
            )
    except Exception:
        pass

    # PDF generators often split one visual font family across differently
    # named subsets (and sometimes mislabel Arabic subsets as Arial). Reuse a
    # style-compatible embedded page font before substituting a system font.
    try:
        for font_entry in page.get_fonts(full=True):
            xref = font_entry[0]
            basefont = font_entry[3]
            if xref == 0 or _font_key(basefont) == clean_target:
                continue
            candidate_bold, candidate_italic = infer_font_style(basefont, 0)
            if candidate_bold != bold or candidate_italic != italic:
                continue
            if _family_stem(basefont) != _family_stem(embedded_font_name):
                continue
            font_tuple = doc.extract_font(xref)
            font_bytes: bytes | None = font_tuple[3] if font_tuple else None
            if not font_bytes:
                continue
            try:
                font = fitz.Font(fontbuffer=font_bytes)
            except Exception:
                continue
            if not (
                _all_glyphs_present(font, new_text)
                or _all_glyphs_shapable(font, new_text)
            ):
                continue
            safe_name = re.sub(r"[^A-Za-z0-9]", "_", _strip_subset_prefix(basefont)) or "EmbFont"
            return FontResolution(
                tier="A",
                fontname=safe_name,
                fontbuffer=font_bytes,
                css_family=safe_name,
            )
    except Exception:
        pass
    return None


# ── System-installed family match ─────────────────────────────────────────────

_IGNORE_TOKENS = {"mt", "ps", "std", "pro", "wgl", "ident"}

_STYLE_TOKENS = {
    "bold": "bold",
    "bd": "bold",
    "black": "bold",
    "heavy": "bold",
    "semibold": "semibold",
    "demibold": "semibold",
    "demi": "semibold",
    "medium": "semibold",
    "italic": "italic",
    "oblique": "italic",
    "it": "italic",
    "regular": "regular",
    "roman": "regular",
    "normal": "regular",
    "rg": "regular",
    "light": "light",
}

_GENERIC_FAMILY_KEYS = {
    "",
    "helv",
    "helvetica",
    "times",
    "timesroman",
    "timesnewroman",
    "courier",
    "cour",
    "sans",
    "serif",
    "mono",
    "type3",
}

_WIN_SHORT_NAMES = {
    "arial": ("arial", {"regular"}),
    "arialbd": ("arial", {"bold"}),
    "ariali": ("arial", {"italic"}),
    "arialbi": ("arial", {"bold", "italic"}),
    "arialn": ("arialnarrow", {"regular"}),
    "arialnb": ("arialnarrow", {"bold"}),
    "arialni": ("arialnarrow", {"italic"}),
    "arialnbi": ("arialnarrow", {"bold", "italic"}),
    "calibri": ("calibri", {"regular"}),
    "calibrib": ("calibri", {"bold"}),
    "calibrii": ("calibri", {"italic"}),
    "calibriz": ("calibri", {"bold", "italic"}),
    "times": ("timesnewroman", {"regular"}),
    "timesbd": ("timesnewroman", {"bold"}),
    "timesi": ("timesnewroman", {"italic"}),
    "timesbi": ("timesnewroman", {"bold", "italic"}),
}


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif system == "Darwin":
        dirs.extend([
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            home / "Library" / "Fonts",
        ])
    else:
        dirs.extend([
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            home / ".fonts",
            home / ".local/share/fonts",
        ])
    return [path for path in dirs if path.is_dir()]


def _parse_font_filename(stem: str) -> tuple[str, set[str]]:
    short = _WIN_SHORT_NAMES.get(stem.lower())
    if short:
        return short
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", spaced) if tok]
    styles: set[str] = set()
    family_parts: list[str] = []
    for token in tokens:
        low = token.lower()
        if low in _IGNORE_TOKENS or token.isdigit():
            continue
        mapped = _STYLE_TOKENS.get(low)
        if mapped:
            styles.add(mapped)
        else:
            family_parts.append(token)
    if not styles:
        styles.add("regular")
    return ("".join(family_parts).lower(), styles)


def _family_stem(name: str) -> str:
    """NotoSans-Regular / Noto Sans Bold / Arial-BoldMT → notosans / arial."""
    return _parse_font_filename(_strip_subset_prefix(name))[0]


def display_family(name: str) -> str:
    """CSS-style family: 'ABCDEF+NotoSans-Regular' → 'Noto Sans'."""
    stripped = _strip_subset_prefix(name)
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", stripped)
    parts: list[str] = []
    for token in re.split(r"[^A-Za-z0-9]+", spaced):
        if not token or token.isdigit():
            continue
        low = token.lower()
        if low in _STYLE_TOKENS or low in _IGNORE_TOKENS:
            continue
        parts.append(token)
    return " ".join(parts) or stripped


def _is_generic_family(name: str) -> bool:
    key = _family_stem(name) or _family_key(name)
    return key in _GENERIC_FAMILY_KEYS or key.startswith("type3")


def _find_font_entry(page: fitz.Page, font_name: str):
    try:
        entries = page.get_fonts(full=True)
    except Exception:
        return None
    match = _TYPE3_XREF_RE.search(font_name or "")
    if match:
        xref = int(match.group(1))
        for entry in entries:
            if int(entry[0]) == xref:
                return entry
        return None
    target = _font_key(font_name)
    for entry in entries:
        basefont, resname = str(entry[3]), str(entry[4])
        if font_name in {basefont, resname}:
            return entry
        if target and target in {_font_key(basefont), _font_key(resname)}:
            return entry
    return None


def _parse_font_descriptor(doc: fitz.Document, xref: int) -> SourceFace | None:
    try:
        obj = doc.xref_object(xref) or ""
    except Exception:
        return None
    fd_match = re.search(r"/FontDescriptor\s+(\d+)\s+0\s+R", obj)
    if not fd_match:
        return None
    try:
        fd_obj = doc.xref_object(int(fd_match.group(1))) or ""
    except Exception:
        return None
    fam_match = re.search(r"/FontFamily\s*\(([^)]*)\)", fd_obj)
    name_match = re.search(r"/FontName\s*/([^\s/]+)", fd_obj)
    weight_match = re.search(r"/FontWeight\s+(\d+)", fd_obj)
    italic_match = re.search(r"/ItalicAngle\s+(-?\d+(?:\.\d+)?)", fd_obj)
    face = _strip_subset_prefix(name_match.group(1) if name_match else "")
    family = (fam_match.group(1) if fam_match else "").strip() or display_family(face)
    weight = int(weight_match.group(1)) if weight_match else 0
    italic = bool(italic_match and abs(float(italic_match.group(1))) > 0.1)
    name_bold, name_italic = infer_font_style(face, 0)
    if weight <= 0:
        weight = 700 if name_bold else 400
    return SourceFace(
        family=family,
        face=face or family,
        weight=weight,
        italic=italic or name_italic,
    )


def source_face_style(
    doc: fitz.Document,
    page: fitz.Page,
    font_name: str,
    flags: int = 0,
) -> SourceFace:
    """Resolve family/weight for whatever font a span used — not only Type3."""
    name_bold, name_italic = infer_font_style(font_name, flags)
    fallback = SourceFace(
        family=display_family(font_name),
        face=_strip_subset_prefix(font_name),
        weight=700 if name_bold else 400,
        italic=name_italic,
    )
    entry = _find_font_entry(page, font_name)
    if entry is None:
        return fallback
    parsed = _parse_font_descriptor(doc, int(entry[0]))
    if parsed is None:
        return fallback
    family = parsed.family or fallback.family
    if _is_generic_family(family) and not _is_generic_family(fallback.family):
        family = fallback.family
    weight = parsed.weight if parsed.weight > 0 else fallback.weight
    # Flags/name can mark a face bold while FontWeight is still 400 (subsets).
    # Keep a numeric medium/semibold from the descriptor; only recover when
    # the descriptor looks regular and the original span was clearly bolder.
    if fallback.weight >= 600 and weight < 500:
        weight = fallback.weight
    return SourceFace(
        family=family,
        face=parsed.face or fallback.face,
        weight=weight,
        italic=parsed.italic or fallback.italic,
    )


def _style_penalty(
    file_styles: set[str],
    bold: bool,
    italic: bool,
    weight: int | None,
) -> int:
    want_italic = italic
    want_semi = weight is not None and 500 <= weight < 650
    want_bold = (not want_semi) and (bold or (weight is not None and weight >= 650))
    penalty = 0
    has_italic = "italic" in file_styles
    if want_italic != has_italic:
        penalty += 80
    if want_semi:
        if "semibold" in file_styles:
            penalty += 0
        elif "bold" in file_styles:
            penalty += 8
        elif "regular" in file_styles:
            penalty += 20
        else:
            penalty += 40
    elif want_bold:
        if "bold" in file_styles and "semibold" not in file_styles:
            penalty += 0
        elif "semibold" in file_styles:
            penalty += 10
        else:
            penalty += 40
    else:
        if file_styles & {"bold", "semibold", "light"}:
            penalty += 40
    return penalty


def _try_system_font(
    family: str,
    bold: bool,
    italic: bool,
    new_text: str,
    weight: int | None = None,
) -> FontResolution | None:
    """Reuse an installed TTF/OTF of the original family when subsets are incomplete."""
    if not family or _is_generic_family(family):
        return None
    target = _family_stem(family)
    if not target:
        return None

    scored: list[tuple[int, Path]] = []
    for folder in _system_font_dirs():
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            file_family, file_styles = _parse_font_filename(path.stem)
            if file_family != target:
                continue
            penalty = _style_penalty(file_styles, bold, italic, weight)
            if penalty >= 80:
                continue
            scored.append((penalty, path))

    scored.sort(key=lambda item: (item[0], len(item[1].stem)))
    for _penalty, path in scored[:12]:
        try:
            font_bytes = path.read_bytes()
            font = fitz.Font(fontbuffer=font_bytes)
        except Exception:
            continue
        if not (
            _all_glyphs_present(font, new_text)
            or _all_glyphs_shapable(font, new_text)
        ):
            continue
        style = "Bold" if bold else "Regular"
        if italic:
            style += "Italic"
        safe_name = re.sub(r"[^A-Za-z0-9]", "_", f"{display_family(family)}{style}") or "SysFont"
        return FontResolution(
            tier="A",
            fontname=safe_name[:40],
            fontbuffer=font_bytes,
            css_family=display_family(family),
        )
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_font(
    doc: fitz.Document,
    page: fitz.Page,
    embedded_font_name: str,
    bold: bool,
    italic: bool,
    new_text: str,
    source_family: str = "",
    weight: int | None = None,
) -> FontResolution:
    """
    Resolve the best available font for reinserting new_text.

    Raises ValueError with a user-visible message if no tier has complete
    glyph coverage (never emit tofu).
    """
    face = source_face_style(doc, page, embedded_font_name)
    source_family = source_family or face.family
    if weight is None:
        weight = face.weight
    if not bold:
        bold = face.bold
    if not italic:
        italic = face.italic

    # Tier A: reuse embedded bytes
    if embedded_font_name:
        res_a = _try_tier_a(doc, page, embedded_font_name, bold, italic, new_text)
        if res_a is not None:
            return res_a

    search_family = source_family or _strip_subset_prefix(embedded_font_name)
    res_sys = _try_system_font(search_family, bold, italic, new_text, weight)
    if res_sys is not None:
        return res_sys

    # Tier B: Base-14 family match
    family_hint = _guess_family(source_family or embedded_font_name)
    b14 = _base14_name(family_hint, bold, italic)
    try:
        b14_font = fitz.Font(b14)
        if _all_glyphs_present(b14_font, new_text):
            return FontResolution(tier="B", fontname=b14, css_family=b14)
    except Exception:
        pass

    # Tier C: broad-script FiraGO, then Ubuntu (both OFL licensed).
    fig_name = _firago_fontname(bold, italic)
    try:
        fig_buf = pymupdf_fonts.fontbuffers[fig_name]()
        fig_font = fitz.Font(fontbuffer=fig_buf)
        if _all_glyphs_present(fig_font, new_text):
            return FontResolution(
                tier="C",
                fontname=fig_name,
                fontbuffer=fig_buf,
                css_family="FiraGO",
            )
    except Exception:
        pass

    ub_name = _ubuntu_fontname(bold, italic)
    try:
        ub_buf = pymupdf_fonts.fontbuffers[ub_name]()
        ub_font = fitz.Font(fontbuffer=ub_buf)
        missing = _missing_glyphs(ub_font, new_text)
        if missing:
            codepoints = ", ".join(
                f"U+{ord(c):04X} ({c!r})" for c in sorted(set(missing))
            )
            raise ValueError(
                "Editing existing text isn't supported for this script. "
                f"Missing glyphs in fallback font: {codepoints}"
            )
        return FontResolution(tier="C", fontname=ub_name, fontbuffer=ub_buf, css_family="Ubuntu")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Font resolution failed: {exc}. "
            "Try pasting plain ASCII text or contact support."
        ) from exc
