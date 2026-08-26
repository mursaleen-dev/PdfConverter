"""Type3 font reuse: parse CMaps, encode replacement text, apply edits."""
from __future__ import annotations

import fitz

from app.routers.text_edit import apply_text_edits
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
