"""Quick test: insert_htmlbox with Ubuntu @font-face data URL."""
import base64
import fitz
import pymupdf_fonts


def test_htmlbox_ubuntu():
    doc = fitz.open()
    page = doc.new_page()
    buf = pymupdf_fonts.fontbuffers["ubuntu"]()
    b64 = base64.b64encode(buf).decode()
    css = (
        "@font-face {"
        'font-family: "Ubuntu";'
        'src: url("data:font/ttf;base64,' + b64 + '");'
        "}"
    )
    html = '<span style="font-family:Ubuntu;font-size:12pt;color:#000000">Hello World — Unicode test: café ümlaut</span>'
    rc = page.insert_htmlbox(fitz.Rect(50, 50, 400, 100), html, css=css)
    print("insert_htmlbox return value:", rc)
    assert rc >= 0, "insert_htmlbox returned negative value"
    out = fitz.open()
    out.insert_pdf(doc)
    import io
    buf2 = io.BytesIO()
    out.save(buf2)
    print("PDF size:", buf2.tell(), "bytes")
    doc.close()
    out.close()


if __name__ == "__main__":
    test_htmlbox_ubuntu()
    print("OK")
