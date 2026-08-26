import uuid
from pathlib import Path

import fitz
from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.config import settings
from app.errors import ConversionError
from app.utils.tempdir import cleanup_dir, scratch_dir
from app.utils.validation import check_size, get_extension

router = APIRouter()


@router.post("/api/merge")
async def merge(files: list[UploadFile]) -> FileResponse:
    if len(files) < 2:
        raise ConversionError(400, "not_enough_files", "Select at least 2 PDF files to merge.")

    with scratch_dir() as tmp_dir:
        try:
            max_bytes = settings.max_upload_bytes
            input_paths: list[Path] = []

            for f in files:
                extension = get_extension(f.filename)
                if extension != ".pdf":
                    raise ConversionError(
                        400, "unsupported_type", f"'{f.filename}' is not a PDF file."
                    )

                path = tmp_dir / f"{uuid.uuid4().hex}.pdf"
                size = 0
                with open(path, "wb") as out:
                    while chunk := await f.read(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            break
                        out.write(chunk)
                check_size(size, max_bytes)
                input_paths.append(path)

            merged = fitz.open()
            try:
                for path in input_paths:
                    try:
                        with fitz.open(path) as src:
                            merged.insert_pdf(src)
                    except Exception as exc:
                        raise ConversionError(
                            422, "unreadable_file", "One of the PDF files could not be read."
                        ) from exc

                output_path = tmp_dir / "merged.pdf"
                merged.save(output_path)
            finally:
                merged.close()
        except Exception:
            cleanup_dir(tmp_dir)
            raise

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="merged.pdf",
            background=BackgroundTask(cleanup_dir, tmp_dir),
        )
