"""
Font resolution for Phase 3 text edits.

Tier A  Reuse bytes from an embedded PDF font (with per-glyph coverage check).
        Type3 fonts are handled separately in type3_fonts (no extractable bytes).
Tier B  Family-matched Base-14 font (Helvetica / Times / Courier).
Tier C  Ubuntu OFL fonts from pymupdf-fonts (broad Latin/Greek/Cyrillic coverage).

If no tier has glyph coverage for every character in new_text, raise ValueError
with a message naming the failing codepoints. This is a hard block — never emit
tofu or corrupt glyphs.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
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


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_font(
    doc: fitz.Document,
    page: fitz.Page,
    embedded_font_name: str,
    bold: bool,
    italic: bool,
    new_text: str,
) -> FontResolution:
    """
    Resolve the best available font for reinserting new_text.

    Raises ValueError with a user-visible message if no tier has complete
    glyph coverage (never emit tofu).
    """
    # Tier A: reuse embedded bytes
    if embedded_font_name:
        res_a = _try_tier_a(doc, page, embedded_font_name, bold, italic, new_text)
        if res_a is not None:
            return res_a

    # Tier B: Base-14 family match
    family_hint = _guess_family(embedded_font_name)
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
