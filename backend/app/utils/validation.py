from pathlib import PurePosixPath

from app.errors import ConversionError


def get_extension(filename: str | None) -> str:
    if not filename:
        raise ConversionError(400, "unsupported_type", "No filename provided.")

    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def check_extension(extension: str, accepted_extensions: frozenset[str]) -> None:
    if extension not in accepted_extensions:
        allowed = ", ".join(sorted(accepted_extensions))
        raise ConversionError(
            400,
            "unsupported_type",
            f"Unsupported file type '{extension or 'unknown'}'. Allowed types: {allowed}.",
        )


def check_size(size_bytes: int, max_bytes: int) -> None:
    if size_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise ConversionError(
            413,
            "file_too_large",
            f"File exceeds the maximum allowed size of {max_mb} MB.",
        )
