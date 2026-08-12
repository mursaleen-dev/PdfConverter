"""
Font resolution for Phase 3 text edits.

Tier A  Reuse bytes from an embedded PDF font (with per-glyph coverage check).
Tier B  Family-matched Base-14 font (Helvetica / Times / Courier).
Tier C  Ubuntu OFL fonts from pymupdf-fonts (broad Latin/Greek/Cyrillic coverage).

If no tier has glyph coverage for every character in new_text, raise ValueError
with a message naming the failing codepoints. This is a hard block — never emit
tofu or corrupt glyphs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import fitz
import pymupdf_fonts


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


# ── Tier A: extract embedded font bytes ──────────────────────────────────────

def _strip_subset_prefix(name: str) -> str:
    """Remove 'ABCDEF+' subset prefix from a PDF font name."""
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def _try_tier_a(
    doc: fitz.Document,
    page: fitz.Page,
    embedded_font_name: str,
    new_text: str,
) -> FontResolution | None:
    """
    Try to reuse the embedded font.  Returns FontResolution if usable, else None.
    """
    clean_target = _strip_subset_prefix(embedded_font_name).lower()
    if not clean_target:
        return None

    try:
        for font_entry in page.get_fonts(full=True):
            xref = font_entry[0]
            basefont = font_entry[3]            # 4th element
            if xref == 0:
                continue
            clean_bf = _strip_subset_prefix(basefont).lower()
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

            if not _all_glyphs_present(font, new_text):
                return None   # embedded font can't render the new characters

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
        res_a = _try_tier_a(doc, page, embedded_font_name, new_text)
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

    # Tier C: Ubuntu (pymupdf-fonts, OFL licensed)
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
