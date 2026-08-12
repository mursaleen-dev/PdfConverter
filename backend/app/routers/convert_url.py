import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.converters.office_converter import convert_office_to_pdf
from app.utils.ssrf import safe_fetch_html
from app.utils.tempdir import cleanup_dir, scratch_dir

router = APIRouter()


class ConvertUrlRequest(BaseModel):
    url: str = Field(..., max_length=2048)


@router.post("/api/convert-url")
async def convert_url(payload: ConvertUrlRequest) -> FileResponse:
    html_bytes = safe_fetch_html(payload.url)

    with scratch_dir() as tmp_dir:
        try:
            input_path = tmp_dir / f"{uuid.uuid4().hex}.html"
            input_path.write_bytes(html_bytes)
            result = convert_office_to_pdf(input_path, tmp_dir)
        except Exception:
            cleanup_dir(tmp_dir)
            raise

        return FileResponse(
            result.path,
            media_type=result.media_type,
            filename="webpage.pdf",
            background=BackgroundTask(cleanup_dir, tmp_dir),
        )
