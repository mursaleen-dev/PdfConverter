from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConversionResult:
    path: Path
    media_type: str
