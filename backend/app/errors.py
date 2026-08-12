from fastapi import Request
from fastapi.responses import JSONResponse


class ConversionError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


async def conversion_error_handler(request: Request, exc: ConversionError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )
