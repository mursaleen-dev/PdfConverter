import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def scratch_dir() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="convert_"))
    try:
        yield path
    finally:
        pass


def cleanup_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
