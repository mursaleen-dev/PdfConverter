"""
Regression runner for the PDF -> Word pipeline (app/converters/pdf_word/).

Runs every PDF in ./samples/ (synthetic templates covering different
structural patterns, plus any real-world PDFs dropped in there) through the
actual production entry point used by POST /api/convert
(app.converters.pdf_converter.convert_pdf_to_docx), not the internal
functions directly -- so this exercises exactly what a live upload would
hit, including the scanned-PDF rejection path.

For each sample:
  - Records whether conversion succeeded, failed with a ConversionError
    (e.g. correctly rejecting a scanned PDF), or crashed unexpectedly.
  - Renders the resulting .docx back to PDF via LibreOffice and reports the
    output page count next to the input page count, so an unexpected page
    increase (a common symptom of a layout regression) is visible at a
    glance.
  - Extracts total text length from input vs output as a rough content-loss
    sanity check.

This won't catch subtle layout misplacement -- for that, render the output
and look at it (see README.md in this directory) -- but it catches crashes,
silent content loss, and page-count blowups across every sample in seconds,
which is exactly what's needed before trusting that an Airblue-specific fix
didn't break something else.

Run: python run_regression.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).parent
SAMPLES_DIR = HERE / "samples"
OUTPUT_DIR = HERE / "output"
BACKEND_ROOT = HERE.parent.parent

sys.path.insert(0, str(BACKEND_ROOT))

from app.converters.pdf_converter import convert_pdf_to_docx  # noqa: E402
from app.errors import ConversionError  # noqa: E402


def _find_soffice() -> str | None:
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    for fallback in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
    ):
        if Path(fallback).is_file():
            return fallback
    return None


def _pdf_page_count_and_text_len(pdf_path: Path) -> tuple[int, int]:
    doc = fitz.open(pdf_path)
    text_len = sum(len(page.get_text()) for page in doc)
    pages = doc.page_count
    doc.close()
    return pages, text_len


def _docx_to_pdf(docx_path: Path, out_dir: Path, soffice: str) -> Path | None:
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
        capture_output=True, text=True, timeout=60,
    )
    out_pdf = out_dir / (docx_path.stem + ".pdf")
    return out_pdf if out_pdf.exists() else None


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    soffice = _find_soffice()
    if not soffice:
        print("LibreOffice not found -- page-count/render checks will be skipped.")

    samples = sorted(SAMPLES_DIR.glob("*.pdf"))
    if not samples:
        print(f"No sample PDFs found in {SAMPLES_DIR}. Run generate_samples.py first.")
        return 1

    rows = []
    any_unexpected_failure = False

    for pdf_path in samples:
        name = pdf_path.name
        in_pages, in_text_len = _pdf_page_count_and_text_len(pdf_path)

        sample_out_dir = OUTPUT_DIR / pdf_path.stem
        sample_out_dir.mkdir(exist_ok=True)

        status = "OK"
        out_pages = "-"
        out_text_len = "-"
        note = ""

        try:
            result = convert_pdf_to_docx(pdf_path, sample_out_dir)
            docx_path = result.path

            if soffice:
                rendered_pdf = _docx_to_pdf(docx_path, sample_out_dir, soffice)
                if rendered_pdf:
                    out_pages, out_text_len = _pdf_page_count_and_text_len(rendered_pdf)
                    if isinstance(out_pages, int) and out_pages > in_pages:
                        note = f"PAGE COUNT INCREASED ({in_pages} -> {out_pages})"
                        status = "WARN"
                    if isinstance(out_text_len, int) and in_text_len > 0:
                        ratio = out_text_len / in_text_len
                        if ratio < 0.5:
                            note = (note + "; " if note else "") + f"TEXT LOSS ({ratio:.0%} of input retained)"
                            status = "WARN"
                else:
                    note = "LibreOffice render-back failed"
                    status = "WARN"

        except ConversionError as e:
            # Expected for e.g. scanned_page.pdf -- report the code, not a failure.
            status = "REJECTED"
            note = f"{e.code}: {e.message}"

        except Exception as e:
            status = "CRASH"
            note = f"{type(e).__name__}: {e}"
            any_unexpected_failure = True

        rows.append((name, in_pages, out_pages, status, note))

    # Print summary table
    print(f"\n{'Sample':<28} {'In pg':<7} {'Out pg':<7} {'Status':<10} Note")
    print("-" * 100)
    for name, in_pages, out_pages, status, note in rows:
        print(f"{name:<28} {in_pages:<7} {str(out_pages):<7} {status:<10} {note}")

    n_crash = sum(1 for r in rows if r[3] == "CRASH")
    n_warn = sum(1 for r in rows if r[3] == "WARN")
    n_ok = sum(1 for r in rows if r[3] == "OK")
    n_rejected = sum(1 for r in rows if r[3] == "REJECTED")
    print(f"\n{n_ok} OK, {n_warn} WARN, {n_rejected} REJECTED (expected for scanned pages), {n_crash} CRASH")

    return 1 if any_unexpected_failure else 0


if __name__ == "__main__":
    sys.exit(main())
