from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.converters.image_converter import convert_image_to_pdf
from app.converters.office_converter import (
    convert_office_to_pdf,
    convert_pdf_to_pdfa,
)
from app.converters.pdf_converter import (
    convert_pdf_to_docx,
    convert_pdf_to_jpg,
    convert_pdf_to_png,
    convert_pdf_to_pptx,
    convert_pdf_to_text,
    convert_pdf_to_xlsx,
)
from app.converters.result import ConversionResult

Converter = Callable[[Path, Path], ConversionResult]


@dataclass
class ToolSpec:
    accepted_extensions: frozenset[str]
    convert: Converter


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "jpg-to-pdf": ToolSpec(frozenset({".jpg", ".jpeg"}), convert_image_to_pdf),
    "png-to-pdf": ToolSpec(frozenset({".png"}), convert_image_to_pdf),
    "word-to-pdf": ToolSpec(frozenset({".doc", ".docx"}), convert_office_to_pdf),
    "excel-to-pdf": ToolSpec(frozenset({".xls", ".xlsx"}), convert_office_to_pdf),
    "powerpoint-to-pdf": ToolSpec(frozenset({".ppt", ".pptx"}), convert_office_to_pdf),
    "text-to-pdf": ToolSpec(frozenset({".txt"}), convert_office_to_pdf),
    "pdf-to-jpg": ToolSpec(frozenset({".pdf"}), convert_pdf_to_jpg),
    "pdf-to-png": ToolSpec(frozenset({".pdf"}), convert_pdf_to_png),
    "pdf-to-text": ToolSpec(frozenset({".pdf"}), convert_pdf_to_text),
    "pdf-to-pdfa": ToolSpec(frozenset({".pdf"}), convert_pdf_to_pdfa),
    "pdf-to-word": ToolSpec(frozenset({".pdf"}), convert_pdf_to_docx),
    "pdf-to-excel": ToolSpec(frozenset({".pdf"}), convert_pdf_to_xlsx),
    "pdf-to-powerpoint": ToolSpec(frozenset({".pdf"}), convert_pdf_to_pptx),
}
