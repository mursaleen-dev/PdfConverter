"""
Generate a small set of synthetic PDFs covering structurally different
layouts, used as a regression suite for the PDF->Word pipeline
(app/converters/pdf_word/). Each sample targets a specific mechanism so a
change that fixes one document's rendering can be checked against the
others before being considered safe.

Run: python generate_samples.py
Writes PDFs into ./samples/
"""
import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


def _make_png_bytes(w: int, h: int, color: tuple) -> bytes:
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    d.rectangle([2, 2, w - 3, h - 3], outline=(255, 255, 255), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- 1. Plain single-column text -------------------------------------------

def make_plain_text():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter
    y = 72
    page.insert_text((72, y), "Quarterly Report", fontsize=18, fontname="helv")
    y += 30
    paragraphs = [
        "This document summarizes performance for the quarter. Revenue grew "
        "steadily across all regions, with the strongest gains in the "
        "northeast territory.",
        "Operating costs remained flat year over year, driven by efficiency "
        "improvements in the supply chain and a reduction in overtime hours "
        "across manufacturing sites.",
        "Looking ahead, the team expects continued growth next quarter, "
        "contingent on stable input costs and no material disruption to "
        "logistics partners.",
    ]
    for para in paragraphs:
        words = para.split()
        line = ""
        for w2 in words:
            if len(line) + len(w2) > 80:
                page.insert_text((72, y), line, fontsize=11, fontname="helv")
                y += 16
                line = w2
            else:
                line = (line + " " + w2).strip()
        if line:
            page.insert_text((72, y), line, fontsize=11, fontname="helv")
            y += 16
        y += 12
    doc.save(SAMPLES_DIR / "plain_text.pdf")
    doc.close()


# --- 2. Two-column resume-style layout --------------------------------------

def make_multi_column_resume():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Jordan Smith", fontsize=20, fontname="helv")
    page.insert_text((72, 92), "Software Engineer", fontsize=12, color=(0.4, 0.4, 0.4))

    # Left narrow column: contact info stacked
    ly = 130
    for line in ["jordan@example.com", "+1 555-0100", "San Francisco, CA", "linkedin.com/in/jsmith"]:
        page.insert_text((72, ly), line, fontsize=9)
        ly += 16

    # Right wide column: experience, starting at same y as left column
    ry = 130
    page.insert_text((220, ry), "EXPERIENCE", fontsize=11, fontname="helv")
    ry += 20
    page.insert_text((220, ry), "Senior Engineer - Acme Corp (2022-Present)", fontsize=10, fontname="helv")
    ry += 15
    for line in [
        "Led migration of core services to a new platform, cutting latency 40%.",
        "Mentored 3 junior engineers and ran the team's on-call rotation.",
    ]:
        page.insert_text((220, ry), line, fontsize=9)
        ry += 14
    ry += 10
    page.insert_text((220, ry), "Engineer - Beta Inc (2019-2022)", fontsize=10, fontname="helv")
    ry += 15
    for line in [
        "Built internal tooling used by 50+ engineers daily.",
        "Shipped the v2 API redesign end to end.",
    ]:
        page.insert_text((220, ry), line, fontsize=9)
        ry += 14

    doc.save(SAMPLES_DIR / "multi_column_resume.pdf")
    doc.close()


# --- 3. Bordered invoice table -----------------------------------------------

def make_invoice_table():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "INVOICE #1042", fontsize=16, fontname="helv")
    page.insert_text((72, 92), "Acme Corp - 123 Market St", fontsize=10)

    cols = [72, 200, 340, 440, 540]
    headers = ["Item", "Qty", "Unit Price", "Total"]
    rows = [
        ["Widget A", "3", "$10.00", "$30.00"],
        ["Widget B", "1", "$25.00", "$25.00"],
        ["Service fee", "1", "$15.00", "$15.00"],
    ]
    top = 130
    row_h = 24
    n_rows = len(rows) + 1

    # Grid lines
    for i in range(n_rows + 1):
        y = top + i * row_h
        page.draw_line((cols[0], y), (cols[-1], y), color=(0, 0, 0), width=0.75)
    for x in cols:
        page.draw_line((x, top), (x, top + n_rows * row_h), color=(0, 0, 0), width=0.75)

    for ci, h in enumerate(headers):
        page.insert_text((cols[ci] + 5, top + 16), h, fontsize=10, fontname="helv")
    for ri, row in enumerate(rows):
        ry = top + (ri + 1) * row_h + 16
        for ci, val in enumerate(row):
            page.insert_text((cols[ci] + 5, ry), val, fontsize=9)

    page.insert_text((400, top + n_rows * row_h + 30), "Total: $70.00", fontsize=11, fontname="helv")
    doc.save(SAMPLES_DIR / "invoice_table.pdf")
    doc.close()


# --- 4. Rows separated by divider lines (Airblue-style header pattern) -----

def make_divider_rows():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page_w = 612

    def divider(y):
        page.draw_line((40, y), (page_w - 40, y), color=(0.5, 0.5, 0.5), width=0.75)

    y = 60
    page.insert_text((40, y), "STATEMENT", fontsize=16, fontname="helv")
    page.insert_text((450, y), "REF: 88213", fontsize=10)
    y += 20
    divider(y)
    y += 25

    # Row: two label/value pairs side by side, same y-band
    page.insert_text((40, y), "Issued: Jan 1, 2026", fontsize=9)
    page.insert_text((350, y), "Due: Jan 31, 2026", fontsize=9)
    y += 20
    divider(y)
    y += 25

    # Row: three items side by side
    page.insert_text((40, y), "Account Holder", fontsize=9, color=(0.4, 0.4, 0.4))
    page.insert_text((250, y), "Branch", fontsize=9, color=(0.4, 0.4, 0.4))
    page.insert_text((450, y), "Status", fontsize=9, color=(0.4, 0.4, 0.4))
    y += 14
    page.insert_text((40, y), "Alex Rivera", fontsize=11, fontname="helv")
    page.insert_text((250, y), "Downtown", fontsize=11, fontname="helv")
    page.insert_text((450, y), "Active", fontsize=11, fontname="helv")
    y += 20
    divider(y)

    doc.save(SAMPLES_DIR / "divider_rows.pdf")
    doc.close()


# --- 5. Small image beside text on the same row (barcode-like) -------------

def make_image_beside_text():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Reference Code", fontsize=11, fontname="helv")

    logo_bytes = _make_png_bytes(160, 40, (30, 30, 160))
    # Place image to the right of the text, same y-band
    page.insert_image(fitz.Rect(400, 60, 540, 85), stream=logo_bytes)

    page.insert_text((72, 120), "Below-image paragraph text to confirm normal flow continues after the row.", fontsize=9)
    doc.save(SAMPLES_DIR / "image_beside_text.pdf")
    doc.close()


# --- 6. Icon-font-style PUA glyph (crash-safety, not a real icon font) -----

def make_icon_font_glyph():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Contact Info", fontsize=14, fontname="helv")
    # PUA codepoint inserted with a standard font (no real icon glyph
    # available in this environment) -- exercises the PUA-detection and
    # rasterization code path without crashing, even though the rendered
    # glyph itself will just be a fallback box rather than a real icon.
    pua_char = chr(0xE001)
    try:
        page.insert_text((72, 100), pua_char + " 555-0100", fontsize=11, fontname="helv")
    except Exception:
        page.insert_text((72, 100), "555-0100", fontsize=11, fontname="helv")
    page.insert_text((72, 120), "Regular text after the icon-like glyph.", fontsize=10)
    doc.save(SAMPLES_DIR / "icon_font_glyph.pdf")
    doc.close()


# --- 7. Scanned-style page (image-only, no text layer) ---------------------

def make_scanned_page():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    img_bytes = _make_png_bytes(600, 780, (245, 245, 240))
    page.insert_image(fitz.Rect(6, 6, 606, 786), stream=img_bytes)
    doc.save(SAMPLES_DIR / "scanned_page.pdf")
    doc.close()


if __name__ == "__main__":
    make_plain_text()
    make_multi_column_resume()
    make_invoice_table()
    make_divider_rows()
    make_image_beside_text()
    make_icon_font_glyph()
    make_scanned_page()
    print("Generated samples in", SAMPLES_DIR)
    for p in sorted(SAMPLES_DIR.glob("*.pdf")):
        print(" -", p.name)
