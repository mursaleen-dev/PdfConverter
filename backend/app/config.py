import shutil
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WINDOWS_FALLBACKS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]
_LINUX_FALLBACKS = [
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
]
_MACOS_FALLBACKS = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    allowed_origins: str = "http://localhost:3000"
    max_upload_mb: int = 20
    max_pdf_pages: int = 500
    soffice_path: str | None = None
    database_url: str = "sqlite:///./app.db"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def resolve_soffice_path(configured: str | None) -> str | None:
    if configured and Path(configured).is_file():
        return configured

    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found

    for fallback in (*_WINDOWS_FALLBACKS, *_LINUX_FALLBACKS, *_MACOS_FALLBACKS):
        if Path(fallback).is_file():
            return fallback

    return None


settings = Settings()
SOFFICE_PATH = resolve_soffice_path(settings.soffice_path)
