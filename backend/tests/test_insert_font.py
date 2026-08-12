"""Verify: insert_font + insert_text for Ubuntu (Tier C) and embedded font (Tier A)."""
import fitz
import pymupdf_fonts
from io import BytesIO


def test_tier_c_ubuntu():
    doc = fitz.open()
    page = doc.new_page()
    buf = pymupdf_fonts.fontbuffers["ubuntu"]()
    page.insert_font(fontname="Ubuntu", fontbuffer=buf)
    rc = page.insert_text(
        fitz.Point(50, 200),
        "Hello — café ümlaut Unicode test",
        fontsize=12,
        fontname="Ubuntu",
        color=(0, 0, 0),
    )
    print("insert_text rows used:", rc)
    out = BytesIO()
    doc.save(out)
    print("PDF size:", out.tell())
    doc.close()


def test_tier_a_embedded():
    src = fitz.open()
    page = src.new_page()
    buf = pymupdf_fonts.fontbuffers["ubuntu"]()
    page.insert_font(fontname="Ub", fontbuffer=buf)
    page.insert_text(fitz.Point(50, 200), "source text", fontname="Ub")
    raw = BytesIO()
    src.save(raw)
    src.close()

    doc2 = fitz.open(stream=raw.getvalue())
    page2 = doc2[0]
    fonts = page2.get_fonts(full=True)
    print("get_fonts result sample:", fonts[0] if fonts else "none")

    doc3 = fitz.open()
    page3 = doc3.new_page()
    for font_entry in fonts:
        xref = font_entry[0]
        if xref == 0:
            continue
        font_tuple = doc2.extract_font(xref)
        print("extract_font fields:", len(font_tuple), "buf len:", len(font_tuple[3]) if font_tuple[3] else 0)
        if font_tuple[3]:
            page3.insert_font(fontname="ExtFont", fontbuffer=font_tuple[3])
            rc = page3.insert_text(fitz.Point(50, 200), "Re-inserted text", fontsize=12, fontname="ExtFont")
            print("insert_text rc:", rc)

    doc2.close()
    doc3.close()


if __name__ == "__main__":
    test_tier_c_ubuntu()
    print("Tier C: OK")
    test_tier_a_embedded()
    print("Tier A round-trip: OK")
