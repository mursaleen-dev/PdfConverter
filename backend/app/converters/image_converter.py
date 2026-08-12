from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.converters.result import ConversionResult
from app.errors import ConversionError


def convert_image_to_pdf(input_path: Path, out_dir: Path) -> ConversionResult:
    output_path = out_dir / "output.pdf"
    try:
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.convert("RGBA").split()[-1])
                rgb_img = background
            elif img.mode == "P":
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                rgb_img = background
            else:
                rgb_img = img.convert("RGB")

            rgb_img.save(output_path, "PDF", resolution=100.0)
    except UnidentifiedImageError as exc:
        raise ConversionError(
            422, "unreadable_file", "The image file could not be read. It may be corrupted."
        ) from exc

    return ConversionResult(output_path, "application/pdf")
