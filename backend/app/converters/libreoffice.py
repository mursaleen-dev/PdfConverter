"""LibreOffice subprocess wrapper for PDF→Word conversion."""
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple
import fitz  # PyMuPDF for PDF inspection

from app.config import SOFFICE_PATH, settings

logger = logging.getLogger(__name__)

# Subprocess timeout: 10 minutes (matches Celery hard limit)
CONVERSION_TIMEOUT_SECONDS = 600

# Maximum pages; rejection happens at upload time, but re-validate here
MAX_PAGE_COUNT = settings.max_pdf_pages


class ConversionError(Exception):
    """Base conversion error with error code for UI categorization."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class PDFValidationError(ConversionError):
    """PDF structure/content issues."""
    pass


class ConversionTimeoutError(ConversionError):
    """Subprocess exceeded time limit."""
    pass


class PDFInspector:
    """Detect PDF properties (page count, encryption, scanned content)."""

    @staticmethod
    def inspect(pdf_path: Path) -> dict:
        """
        Returns:
            {
                "page_count": int,
                "is_encrypted": bool,
                "is_scanned": bool,  # Heuristic: no text layer or <50% text coverage
                "has_text": bool,
            }
        """
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFValidationError("pdf_corrupted", f"Cannot open PDF: {e}")

        if not doc.is_pdf:
            raise PDFValidationError("not_a_pdf", "File is not a valid PDF")

        page_count = len(doc)
        if page_count > MAX_PAGE_COUNT:
            raise PDFValidationError(
                "page_limit_exceeded",
                f"PDF has {page_count} pages (max {MAX_PAGE_COUNT})"
            )

        is_encrypted = doc.is_encrypted

        # Heuristic for scanned PDFs: check if first 3 pages have text blocks
        has_text = False
        for i, page in enumerate(doc[:3]):
            text_blocks = page.get_text("blocks")
            # Filter to text blocks (type 0) with actual content
            text_content = [b for b in text_blocks if b[6] == 0 and b[4].strip()]
            if text_content:
                has_text = True
                break

        doc.close()
        return {
            "page_count": page_count,
            "is_encrypted": is_encrypted,
            "is_scanned": not has_text,  # No text = likely scanned
            "has_text": has_text,
        }


def convert_pdf_to_docx(
    input_pdf_path: Path,
    output_docx_path: Path,
    timeout_seconds: int = CONVERSION_TIMEOUT_SECONDS,
) -> Tuple[bool, Optional[str]]:
    """
    Convert PDF to DOCX using LibreOffice headless conversion.

    Args:
        input_pdf_path: Path to input PDF
        output_docx_path: Path for output DOCX
        timeout_seconds: Subprocess timeout (default: 10 minutes)

    Returns:
        (success: bool, error_code: Optional[str])
        If success=False, error_code is one of:
            - "soffice_not_found" → LibreOffice not installed
            - "pdf_corrupted" → Cannot parse PDF
            - "not_a_pdf" → File is not a PDF
            - "page_limit_exceeded" → Too many pages
            - "password_protected" → PDF requires password
            - "scanned_pdf" → No extractable text layer
            - "conversion_timeout" → Subprocess exceeded timeout
            - "conversion_failed" → LibreOffice error (generic)
    """
    if not SOFFICE_PATH:
        logger.error("LibreOffice (soffice) not found on system PATH")
        return False, "soffice_not_found"

    # Validate PDF before conversion
    try:
        pdf_info = PDFInspector.inspect(input_pdf_path)
    except PDFValidationError as e:
        logger.warning(f"PDF validation failed: {e.code}")
        return False, e.code

    if pdf_info["is_encrypted"]:
        logger.info(f"PDF is password-protected: {input_pdf_path.name}")
        return False, "password_protected"

    if pdf_info["is_scanned"]:
        logger.info(f"PDF is scanned (no text layer): {input_pdf_path.name}")
        return False, "scanned_pdf"

    # Run LibreOffice conversion
    try:
        output_dir = str(output_docx_path.parent)
        output_name = output_docx_path.name

        cmd = [
            SOFFICE_PATH,
            "--headless",
            # By default LibreOffice opens PDFs in Draw, which has no docx
            # export filter ("no export filter... found, aborting"). Force
            # import through the Writer PDF-import filter so the docx
            # export filter is available on the resulting document.
            "--infilter=writer_pdf_import",
            "--convert-to", "docx",
            "--outdir", output_dir,
            str(input_pdf_path),
        ]

        logger.info(f"Running LibreOffice conversion: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            stderr = result.stderr or result.stdout
            logger.error(f"LibreOffice error (code {result.returncode}): {stderr}")
            return False, "conversion_failed"

        # LibreOffice names its output after the INPUT file's stem, not the
        # output path we requested (--outdir only controls the directory).
        # Our input is a UUID-named temp file, so the actual artifact is
        # "<input-stem>.docx" — rename it to the desired output path.
        actual_output_path = Path(output_dir) / f"{input_pdf_path.stem}.docx"

        if actual_output_path != output_docx_path and actual_output_path.exists():
            actual_output_path.replace(output_docx_path)

        if not output_docx_path.exists():
            logger.error(
                f"LibreOffice produced no output at {output_docx_path} "
                f"(also checked {actual_output_path})"
            )
            return False, "conversion_failed"

        logger.info(f"Conversion succeeded: {input_pdf_path.name} → {output_name}")
        return True, None

    except subprocess.TimeoutExpired:
        logger.error(f"LibreOffice conversion timed out after {timeout_seconds}s")
        return False, "conversion_timeout"
    except Exception as e:
        logger.error(f"Unexpected error during conversion: {e}")
        return False, "conversion_failed"


def get_user_facing_error_message(error_code: str) -> str:
    """Map error codes to user-friendly messages."""
    messages = {
        "soffice_not_found": "LibreOffice is not installed or not found on the system.",
        "pdf_corrupted": "The PDF file appears to be corrupted or invalid.",
        "not_a_pdf": "The uploaded file is not a valid PDF.",
        "page_limit_exceeded": f"PDF exceeds the {MAX_PAGE_COUNT}-page limit.",
        "password_protected": "PDF is password-protected. Please remove the password and try again.",
        "scanned_pdf": "PDF appears to be a scanned image with no extractable text. Text extraction failed.",
        "conversion_timeout": "Conversion took too long. The PDF may be too complex.",
        "conversion_failed": "An error occurred during conversion. Please try again or contact support.",
    }
    return messages.get(error_code, "Unknown error during conversion.")
