"""Type3 font reuse: parse CMaps, encode replacement text, apply edits."""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.routers.text_edit import _build_span_lookup, apply_text_edits
from app.type3_fonts import (
    encode_with_type3,
    parse_tounicode,
    type3_face_style,
    type3_xref_from_name,
)


def _pdf(objects: list[bytes]) -> bytes:
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(sum(len(p) for p in parts))
        parts.append(f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    startxref = sum(len(p) for p in parts)
    xref = [b"xref\n", f"0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    parts.extend(xref)
    parts.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode("ascii")
    )
    return b"".join(parts)


def _stream(payload: bytes) -> bytes:
    return f"<< /Length {len(payload)} >>\nstream\n".encode("ascii") + payload + b"\nendstream"


def make_type3_pdf() -> bytes:
    """Minimal inverted-matrix Type3 font covering A, B, C, space — Archivo-like."""
    tounicode = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
4 beginbfchar
<20> <0020>
<41> <0041>
<42> <0042>
<43> <0043>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    glyph = b"600 0 0 0 600 700 d1\n0 0 600 700 re\nf\n"
    contents = b"BT /F1 12 Tf 1 0 0 -1 40 80 Tm (ABC) Tj ET\n"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type3 /Name /F1 "
        b"/FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 -0.001 0 0] "
        b"/FirstChar 32 /LastChar 67 /Widths [196 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 600 600 600] "
        b"/Encoding << /Type /Encoding /Differences [32 /space 65 /A /B /C] >> "
        b"/CharProcs << /space 6 0 R /A 7 0 R /B 8 0 R /C 9 0 R >> "
        b"/ToUnicode 10 0 R /FontDescriptor 11 0 R >>",
        _stream(contents),
        _stream(b"196 0 0 0 196 100 d1\n"),
        _stream(glyph),
        _stream(glyph),
        _stream(glyph),
        _stream(tounicode),
        b"<< /Type /FontDescriptor /FontFamily (Archivo) /FontStretch /Normal "
        b"/FontWeight 700 /FontName /TestArchivo-Bold /ItalicAngle 0 /Flags 4 >>",
    ])


def make_two_weight_type3_pdf(second_weight: int = 400) -> bytes:
    """Bold Type3 with A/B plus a second face that only has C."""
    tounicode_ab = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
3 beginbfchar
<20> <0020>
<41> <0041>
<42> <0042>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    tounicode_c = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
1 beginbfchar
<43> <0043>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    glyph = b"600 0 0 0 600 700 d1\n0 0 600 700 re\nf\n"
    contents = b"BT /F1 12 Tf 1 0 0 -1 40 80 Tm (AB) Tj ET\n"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R /F2 12 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type3 /Name /F1 "
        b"/FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 -0.001 0 0] "
        b"/FirstChar 32 /LastChar 66 /Widths [196 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 600 600] "
        b"/Encoding << /Type /Encoding /Differences [32 /space 65 /A /B] >> "
        b"/CharProcs << /space 6 0 R /A 7 0 R /B 8 0 R >> "
        b"/ToUnicode 9 0 R /FontDescriptor 10 0 R >>",
        _stream(contents),
        _stream(b"196 0 0 0 196 100 d1\n"),
        _stream(glyph),
        _stream(glyph),
        _stream(tounicode_ab),
        b"<< /Type /FontDescriptor /FontFamily (Archivo) /FontStretch /Normal "
        b"/FontWeight 700 /FontName /TestArchivo-Bold /ItalicAngle 0 /Flags 4 >>",
        (
            b"<< /Type /FontDescriptor /FontFamily (Archivo) /FontStretch /Normal "
            + f"/FontWeight {second_weight} /FontName /TestArchivo-Other /ItalicAngle 0 /Flags 4 >>".encode("ascii")
        ),
        b"<< /Type /Font /Subtype /Type3 /Name /F2 "
        b"/FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 -0.001 0 0] "
        b"/FirstChar 67 /LastChar 67 /Widths [600] "
        b"/Encoding << /Type /Encoding /Differences [67 /C] >> "
        b"/CharProcs << /C 13 0 R >> "
        b"/ToUnicode 14 0 R /FontDescriptor 11 0 R >>",
        _stream(glyph),
        _stream(tounicode_c),
    ])


class TestParseToUnicode:
    def test_bfchar_and_bfrange(self):
        data = b"""
        2 beginbfchar
        <41> <0041>
        <42> <0042>
        endbfchar
        1 beginbfrange
        <48> <49> <006D>
        endbfrange
        """
        mapping = parse_tounicode(data)
        assert mapping[0x41] == "A"
        assert mapping[0x42] == "B"
        assert mapping[0x48] == "m"
        assert mapping[0x49] == "n"


class TestType3Atlas:
    def test_xref_from_span_name(self):
        assert type3_xref_from_name("Type3 (29 0 R)") == 29
        assert type3_xref_from_name("Helvetica") is None

    def test_encodes_named_type3_font(self):
        doc = fitz.open(stream=make_type3_pdf(), filetype="pdf")
        page = doc[0]
        style = type3_face_style(doc, "F1", page)
        assert style is not None
        assert style.family == "Archivo"
        assert style.weight == 700
        layout = encode_with_type3(doc, page, page, "F1", "CAB")
        assert layout is not None
        assert [g.code for g in layout.glyphs] == [0x43, 0x41, 0x42]
        assert layout.face == "TestArchivo-Bold"
        doc.close()

    def test_missing_glyph_returns_none(self):
        doc = fitz.open(stream=make_type3_pdf(), filetype="pdf")
        page = doc[0]
        assert encode_with_type3(doc, page, page, "F1", "Z") is None
        doc.close()


def make_chrome_named_two_page_pdf() -> bytes:
    """Chrome-style Type3: both weights named NotoSans-Regular, dest resources remapped.

    Page 1 uses /F1 (weight 700, glyphs A/B). Page 2 lists /G1 (weight 400,
    glyphs A/B/C) first, then /G2 (the original 700 face). Matching dest by
    face name alone would pick Regular and strip bold.
    """
    tounicode_ab = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
3 beginbfchar
<20> <0020>
<41> <0041>
<42> <0042>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    tounicode_abc = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
4 beginbfchar
<20> <0020>
<41> <0041>
<42> <0042>
<43> <0043>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    glyph = b"600 0 0 0 600 700 d1\n0 0 600 700 re\nf\n"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 15 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type3 /Name /F1 "
        b"/FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 -0.001 0 0] "
        b"/FirstChar 32 /LastChar 66 /Widths [196 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 600 600] "
        b"/Encoding << /Type /Encoding /Differences [32 /space 65 /A /B] >> "
        b"/CharProcs << /space 6 0 R /A 7 0 R /B 8 0 R >> "
        b"/ToUnicode 9 0 R /FontDescriptor 10 0 R >>",
        _stream(b"BT /F1 12 Tf 1 0 0 -1 40 80 Tm (AB) Tj ET\n"),
        _stream(b"196 0 0 0 196 100 d1\n"),
        _stream(glyph),
        _stream(glyph),
        _stream(tounicode_ab),
        b"<< /Type /FontDescriptor /FontFamily (Noto Sans) /FontStretch /Normal "
        b"/FontWeight 700 /FontName /NotoSans-Regular /ItalicAngle 0 /Flags 4 >>",
        b"<< /Type /FontDescriptor /FontFamily (Noto Sans) /FontStretch /Normal "
        b"/FontWeight 400 /FontName /NotoSans-Regular /ItalicAngle 0 /Flags 4 >>",
        b"<< /Type /Font /Subtype /Type3 /Name /G1 "
        b"/FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 -0.001 0 0] "
        b"/FirstChar 32 /LastChar 67 /Widths [196 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 600 600 600] "
        b"/Encoding << /Type /Encoding /Differences [32 /space 65 /A /B /C] >> "
        b"/CharProcs << /space 6 0 R /A 7 0 R /B 8 0 R /C 13 0 R >> "
        b"/ToUnicode 14 0 R /FontDescriptor 11 0 R >>",
        _stream(glyph),
        _stream(tounicode_abc),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /G1 12 0 R /G2 4 0 R >> >> /Contents 16 0 R >>",
        _stream(b"BT /G1 12 Tf 1 0 0 -1 40 80 Tm (C) Tj ET\n"),
    ])


class TestType3WeightIsolation:
    def test_does_not_borrow_lighter_weight_glyphs(self):
        doc = fitz.open(stream=make_two_weight_type3_pdf(), filetype="pdf")
        page = doc[0]
        assert encode_with_type3(doc, page, page, "F1", "C") is None
        layout = encode_with_type3(doc, page, page, "F1", "BA")
        assert layout is not None
        assert [g.resource for g in layout.glyphs] == ["F1", "F1"]
        doc.close()

    def test_remapped_resources_keep_original_weight(self):
        doc = fitz.open(stream=make_chrome_named_two_page_pdf(), filetype="pdf")
        orig, dest = doc[0], doc[1]
        layout = encode_with_type3(doc, orig, dest, "F1", "BA")
        assert layout is not None
        assert layout.weight == 700
        assert [g.resource for g in layout.glyphs] == ["G2", "G2"]
        doc.close()

    def test_reuses_same_weight_subset(self):
        doc = fitz.open(stream=make_two_weight_type3_pdf(second_weight=700), filetype="pdf")
        page = doc[0]
        layout = encode_with_type3(doc, page, page, "F1", "C")
        assert layout is not None
        assert layout.glyphs[0].resource == "F2"
        doc.close()


ITINERARY = Path(r"c:\Users\Dell\Downloads\__ The Travel Itinerary-1.pdf")


def _span_id_for_text(page: fitz.Page, page_id: str, needle: str) -> str:
    raw = page.get_text(
        "rawdict",
        flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES,
    )
    lookup = _build_span_lookup(raw, page_id)
    for span_id, span in lookup.items():
        text = span.get("text") or "".join(char.get("c", "") for char in span.get("chars", []))
        if text.strip() == needle:
            return span_id
    raise AssertionError(f"{needle!r} not found on page")


class TestItineraryAirportCode:
    @pytest.mark.skipif(not ITINERARY.exists(), reason="itinerary sample PDF not present")
    def test_missing_bold_letters_do_not_mix_regular_type3(self):
        orig = fitz.open(ITINERARY)
        page = orig[0]
        assert encode_with_type3(orig, page, page, "Type3 (12 0 R)", "SHJ") is not None
        assert encode_with_type3(orig, page, page, "Type3 (12 0 R)", "LHR") is None
        orig.close()

    @pytest.mark.skipif(not ITINERARY.exists(), reason="itinerary sample PDF not present")
    def test_khi_to_lhr_keeps_one_bold_face(self):
        raw = ITINERARY.read_bytes()
        orig = fitz.open(stream=raw, filetype="pdf")
        rebuilt = fitz.open(stream=raw, filetype="pdf")
        span_id = _span_id_for_text(orig[0], "p0", "KHI")
        warnings = apply_text_edits(
            rebuilt,
            orig,
            {"p0": 0},
            [{"pageId": "p0", "sourceIndex": 0}],
            [{
                "pageId": "p0",
                "spanIds": [span_id],
                "newText": [{"text": "LHR", "sizeScale": 1.0, "color": "#4a4a55"}],
                "overflowPolicy": "overflow",
            }],
        )
        assert warnings == []
        fonts = []
        for block in rebuilt[0].get_text("rawdict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = "".join(char.get("c", "") for char in span.get("chars", []))
                    text = span.get("text") or chars
                    if text in {"L", "H", "R", "LHR"} or "LHR" in text:
                        fonts.append(span.get("font", ""))
        assert fonts, rebuilt[0].get_text()
        assert len(set(fonts)) == 1
        font_name = fonts[0].lower()
        assert "helv" not in font_name
        assert "ubuntu" not in font_name
        orig.close()
        rebuilt.close()

    @pytest.mark.skipif(not ITINERARY.exists(), reason="itinerary sample PDF not present")
    def test_regular_city_name_keeps_regular_face(self):
        raw = ITINERARY.read_bytes()
        orig = fitz.open(stream=raw, filetype="pdf")
        rebuilt = fitz.open(stream=raw, filetype="pdf")
        span_id = _span_id_for_text(orig[0], "p0", "Karachi")
        warnings = apply_text_edits(
            rebuilt,
            orig,
            {"p0": 0},
            [{"pageId": "p0", "sourceIndex": 0}],
            [{
                "pageId": "p0",
                "spanIds": [span_id],
                "newText": [{"text": "Zurich", "sizeScale": 1.0, "color": "#4a4a55"}],
                "overflowPolicy": "overflow",
            }],
        )
        assert warnings == []
        fonts = [
            span.get("font", "")
            for block in rebuilt[0].get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if "Zurich" in span.get("text", "")
        ]
        assert fonts, rebuilt[0].get_text()
        joined = " ".join(fonts).lower()
        assert "helv" not in joined
        assert "ubuntu" not in joined
        orig.close()
        rebuilt.close()


class TestType3Apply:
    def test_replacement_keeps_type3_font(self):
        raw = make_type3_pdf()
        orig = fitz.open(stream=raw, filetype="pdf")
        rebuilt = fitz.open(stream=raw, filetype="pdf")
        warnings = apply_text_edits(
            rebuilt,
            orig,
            {"p0": 0},
            [{"pageId": "p0", "sourceIndex": 0}],
            [{
                "pageId": "p0",
                "spanIds": ["p0:0:0:0"],
                "newText": [{"text": "CAB", "sizeScale": 1.0, "color": "#1e2e3e"}],
                "overflowPolicy": "overflow",
            }],
        )
        assert warnings == []
        rebuilt_page = rebuilt[0]
        text = rebuilt_page.get_text()
        assert "CAB" in text
        replacement_fonts = [
            span.get("font", "")
            for block in rebuilt_page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if "CAB" in span.get("text", "")
        ]
        assert replacement_fonts, text
        joined = " ".join(replacement_fonts).lower()
        assert "helv" not in joined
        assert "nimbus" not in joined
        orig.close()
        rebuilt.close()
