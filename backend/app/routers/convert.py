import uuid
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.config import SOFFICE_PATH, settings
from app.converters.pdf_converter import convert_pdf_to_docx
from app.errors import ConversionError
from app.tools_registry import TOOL_REGISTRY
from app.utils.tempdir import cleanup_dir, scratch_dir
from app.utils.validation import check_extension, check_size, get_extension

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "soffice_available": SOFFICE_PATH is not None,
        "soffice_path": SOFFICE_PATH,
    }


@router.post("/api/convert")
async def convert(
    file: UploadFile,
    tool: str = Form(...),
    mode: str | None = Form(None),
) -> FileResponse:
    """
    Convert a file using the specified tool. Returns the converted file directly.

    Note: pdf-to-word uses the synchronous, PyMuPDF-based pipeline in
    app/converters/pdf_word/ (layout_analyzer + docx_builder), which preserves
    inline images with correct positioning/sizing. It intentionally does NOT
    use the async LibreOffice pipeline in app/converters/libreoffice.py +
    app/tasks.py — that pipeline's --infilter=writer_pdf_import output
    reconstructs the page as absolutely-positioned frames and was losing
    image visibility. That async infrastructure (ConversionJob model, Celery
    task, /api/jobs/* endpoints) is kept for potential future use (e.g. an
    OCR path for scanned PDFs) but is not wired to any tool right now.
    """
    spec = TOOL_REGISTRY.get(tool)
    if spec is None:
        raise ConversionError(400, "unknown_tool", f"Unknown conversion tool '{tool}'.")

    extension = get_extension(file.filename)
    check_extension(extension, spec.accepted_extensions)

    # Synchronous conversion path (all tools, including pdf-to-word)
    with scratch_dir() as tmp_dir:
        input_path = tmp_dir / f"{uuid.uuid4().hex}{extension}"

        try:
            size = 0
            max_bytes = settings.max_upload_bytes
            with open(input_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        break
                    f.write(chunk)

            check_size(size, max_bytes)

            if tool == "pdf-to-word":
                result = convert_pdf_to_docx(
                    input_path,
                    tmp_dir,
                    mode=mode or "keep-layout",
                )
            else:
                result = spec.convert(input_path, tmp_dir)

            if not result.path.is_file():
                raise ConversionError(
                    500, "conversion_failed", "Conversion did not produce an output file."
                )
        except Exception:
            cleanup_dir(tmp_dir)
            raise

        original_stem = Path(file.filename).stem if file.filename else "converted"
        download_name = f"{original_stem}{result.path.suffix}"

        return FileResponse(
            result.path,
            media_type=result.media_type,
            filename=download_name,
            background=BackgroundTask(cleanup_dir, tmp_dir),
        )
