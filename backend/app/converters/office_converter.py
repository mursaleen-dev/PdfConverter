import subprocess
import tempfile
import logging
from pathlib import Path

import fitz

from app.config import SOFFICE_PATH
from app.converters.result import ConversionResult
from app.errors import ConversionError

logger = logging.getLogger(__name__)


def _run_soffice(input_path: Path, out_dir: Path, filter_name: str, infilter: str | None = None) -> Path:
    if not SOFFICE_PATH:
        raise ConversionError(
            500,
            "converter_unavailable",
            "LibreOffice is not installed or could not be found on this server. "
            "This conversion is unavailable.",
        )

    # Export to a dedicated subdirectory so the output path can never collide with
    # the input path (e.g. pdf-to-pdfa has matching input/output extensions, and
    # LibreOffice cannot overwrite a file it still has open for reading).
    export_dir = out_dir / "export"
    export_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        profile_uri = f"file:///{Path(profile_dir).as_posix()}"
        try:
            cmd = [
                SOFFICE_PATH,
                f"-env:UserInstallation={profile_uri}",
                "--headless",
                "--norestore",
                "--nodefault",
                "--nolockcheck",
                "--nofirststartwizard",
            ]
            if infilter:
                cmd.append(f"--infilter={infilter}")
            cmd += ["--convert-to", filter_name, "--outdir", str(export_dir), str(input_path)]
            result = subprocess.run(
                cmd,
                timeout=120,
                capture_output=True,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(
                504, "conversion_timeout", "The document took too long to convert."
            ) from exc
        except subprocess.CalledProcessError as exc:
            logger.warning("LibreOffice failed: %s", exc.stderr.decode(errors="replace"))
            raise ConversionError(
                422,
                "unreadable_file",
                "The document could not be converted. It may be corrupted or unsupported.",
            ) from exc

    # LibreOffice names the output after the input stem with the target extension,
    # e.g. "pdf:writer_pdf_Export:{...}" still produces "<stem>.pdf".
    output_extension = filter_name.split(":", 1)[0]
    produced = export_dir / f"{input_path.stem}.{output_extension}"
    if not produced.is_file():
        logger.warning("Expected output missing. stdout=%r stderr=%r", result.stdout, result.stderr)
        raise ConversionError(
            500, "conversion_failed", "Conversion did not produce an output file."
        )
    if produced.stat().st_size == 0:
        raise ConversionError(500, "conversion_failed", "Conversion produced an empty output file.")

    return produced


def convert_office_to_pdf(input_path: Path, out_dir: Path) -> ConversionResult:
    produced = _run_soffice(input_path, out_dir, "pdf")
    try:
        with fitz.open(produced) as pdf:
            if not pdf.is_pdf or pdf.page_count == 0:
                raise ValueError("empty PDF")
    except Exception as exc:
        raise ConversionError(
            500,
            "invalid_output",
            "The office document converted, but the resulting PDF is invalid.",
        ) from exc
    return ConversionResult(produced, "application/pdf")


def convert_pdf_to_pdfa(input_path: Path, out_dir: Path) -> ConversionResult:
    pdfa_filter = 'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":2}}'
    produced = _run_soffice(input_path, out_dir, pdfa_filter)
    return ConversionResult(produced, "application/pdf")

