"""Test TextWriter for multi-run text placement."""
import fitz
import pymupdf_fonts
from io import BytesIO


def test_textwriter_multi_run():
    doc = fitz.open()
    page = doc.new_page()

    tw = fitz.TextWriter(page.rect)
    ub_font = fitz.Font(fontbuffer=pymupdf_fonts.fontbuffers["ubuntu"]())
    ub_bold = fitz.Font(fontbuffer=pymupdf_fonts.fontbuffers["ubuntubo"]())

    start = fitz.Point(50, 200)
    result1 = tw.append(start, "Hello ", fontsize=12, font=ub_font)
    print("append result type:", type(result1), result1)

    # Try to use the returned value as next position
    if isinstance(result1, (tuple, list)):
        next_pos = result1[1] if len(result1) > 1 else result1[0]
    else:
        next_pos = result1

    result2 = tw.append(next_pos, "World", fontsize=12, font=ub_bold)
    print("append2 result:", result2)

    tw.write_text(page)
    print("TextWriter ok")

    out = BytesIO()
    doc.save(out)
    print("PDF size:", out.tell())
    doc.close()


if __name__ == "__main__":
    test_textwriter_multi_run()
    print("OK")
