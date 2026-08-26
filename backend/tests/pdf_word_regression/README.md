# PDF -> Word regression suite

Catches crashes, page-count blowups, and content loss across a set of
structurally different PDFs *before* trusting that a fix for one document
(e.g. an Airblue e-ticket) didn't break another (e.g. a resume, an invoice).

## Why this exists

Every layout-reconstruction fix in `app/converters/pdf_word/` up to this
point was diagnosed and verified against a single real-world PDF. That's a
fine way to find bugs, but it's not evidence the fix generalizes — a
threshold tuned by eyeballing one document's measurements can misfire on a
document with different proportions, or fail entirely on a PDF that uses a
different underlying convention (see the `_collect_h_segments` bug below).

## Running it

```bash
cd tests/pdf_word_regression
python generate_samples.py   # (re)generate the synthetic PDFs into samples/
python run_regression.py     # run every PDF in samples/ through the real
                              # production entry point and report results
```

`run_regression.py` calls `app.converters.pdf_converter.convert_pdf_to_docx`
directly — the same function `POST /api/convert` uses — then renders the
result back to PDF via LibreOffice and reports page count and text-length
vs. the input, so a page-count blowup (the most common symptom of a layout
regression) is visible immediately. It does **not** catch subtle
misplacement (e.g. an item landing in the wrong column) — for that, render
a sample and look at it:

```python
import fitz
doc = fitz.open("output/<sample_name>/<sample_name>.pdf")
doc[0].get_pixmap(dpi=150).save("preview.png")
```

## Samples

| File | Exercises |
|---|---|
| `plain_text.pdf` | Baseline single-column paragraph flow |
| `multi_column_resume.pdf` | Two persistent side-by-side columns across multiple paragraph blocks |
| `invoice_table.pdf` | Bordered grid / table detection |
| `divider_rows.pdf` | Rows separated by thin divider rules (drawn as stroked lines, not filled bars) |
| `image_beside_text.pdf` | An image merging into the same row as adjacent text (e.g. a barcode/logo beside a label) |
| `icon_font_glyph.pdf` | PUA-codepoint (icon-font) extraction path, crash-safety only — no real icon font is available in this environment, so the rendered glyph is a fallback box, not a real icon |
| `scanned_page.pdf` | Correctly rejected as `scanned_pdf` before reaching the layout engine |
| `real_airblue_eticket.pdf` | The real-world PDF every prior fix in this pipeline was diagnosed against |

**Add more real-world PDFs here over time** — just drop a `.pdf` into
`samples/` and it's picked up automatically next run. Real documents (a
different invoice, a bank statement, a form, a multi-page report) are more
valuable coverage than more synthetic samples once a few are available.

## Known limitations found by this suite (not yet fixed)

- **Persistent multi-block columns**: `multi_column_resume.pdf` shows a
  real bug — column detection only pairs a paragraph with a sibling that
  overlaps it *at that exact y-band*. A second paragraph further down the
  same column (e.g. a second job entry in a resume's right column) has no
  sibling at its own y-band once the left column has run out of content,
  so it falls back to full-width placement and loses its indentation. This
  is a structural limitation of the current pairwise-row approach — fixing
  it properly needs persistent column-region tracking (closer to how
  `_build_paragraphs`'s track-matching works), not just an overlap
  threshold change. Out of scope for now; documented so it isn't
  rediscovered from scratch.

## Fixed via this suite

- **`_collect_h_segments` silently dropped stroked divider/table lines.**
  `fitz.Rect.is_empty()` is True for a zero-height rect, which is exactly
  what a horizontal *stroked line*'s bounding box looks like (as opposed to
  a thin *filled rectangle*, which has nonzero height). The function
  skipped every such path outright, so divider-line detection (and by
  extension table-border detection, which uses the same function)
  completely failed on any PDF that draws rules with a line-stroke
  operator instead of a filled bar — a very common alternative convention.
  This never showed up against the Airblue PDF because that document
  happens to use filled bars for its dividers. Found via
  `divider_rows.pdf`, fixed in `layout_analyzer.py`.
