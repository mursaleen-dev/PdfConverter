from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import ConversionError, conversion_error_handler
from app.routers.convert import router as convert_router
from app.routers.convert_url import router as convert_url_router
from app.routers.edit import router as edit_router
from app.routers.extract import router as extract_router
from app.routers.jobs import router as jobs_router
from app.routers.merge import router as merge_router
from app.routers.sejda import router as sejda_router
from app.routers.text_edit import router as text_edit_router

app = FastAPI(title="File to PDF Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.add_exception_handler(ConversionError, conversion_error_handler)

app.include_router(convert_router)
app.include_router(convert_url_router)
app.include_router(edit_router)
app.include_router(extract_router)
app.include_router(jobs_router)
app.include_router(merge_router)
app.include_router(sejda_router)
app.include_router(text_edit_router)
