"""Character-level helpers shared by PDF text extraction and editing."""
from __future__ import annotations

import unicodedata
import re
from typing import Any


def _strong_direction(char: str) -> str | None:
    bidi = unicodedata.bidirectional(char)
    if bidi in {"R", "AL", "AN"}:
        return "rtl"
    if bidi in {"L", "EN"}:
        return "ltr"
    return None


def _unicode_script(char: str) -> str | None:
    """Return a stable Unicode script family without language-specific rules."""
    if not char or unicodedata.category(char)[0] in {"M", "N", "P", "S", "Z", "C"}:
        return None
    name = unicodedata.name(char, "")
    if not name:
        return None
    if name.startswith(("CJK ", "IDEOGRAPHIC ")):
        return "HAN"
    # Unicode character names consistently begin with their script for these
    # writing systems. Unknown scripts still get a deterministic first token.
    return name.split(" ", 1)[0]


def infer_font_style(font_name: str, flags: int) -> tuple[bool, bool]:
    """Combine PDF flags with common font-name style markers."""
    normalized = re.sub(r"[^a-z0-9]+", " ", (font_name or "").lower())
    words = set(normalized.split())
    bold = bool(flags & (1 << 4)) or bool(
        words & {"bold", "semibold", "demibold", "demi", "black", "heavy"}
    )
    italic = bool(flags & (1 << 1)) or bool(
        words & {"italic", "oblique", "slanted"}
    )
    return bold, italic


def split_mixed_direction_span(span: dict[str, Any]) -> list[tuple[int, dict[str, Any], str]]:
    """Split a rawdict span at Unicode script or writing-direction boundaries."""
    chars = span.get("chars", [])
    if not chars:
        segment = dict(span)
        segment["_editScript"] = "UNKNOWN"
        return [(0, segment, "ltr")]

    directions = [_strong_direction(char.get("c", "")) for char in chars]
    scripts = [_unicode_script(char.get("c", "")) for char in chars]
    first_direction = next((value for value in directions if value), "ltr")
    first_script = next((value for value in scripts if value), "UNKNOWN")
    resolved: list[tuple[str, str]] = []
    current_direction, current_script = first_direction, first_script
    for direction, script in zip(directions, scripts):
        if direction:
            current_direction = direction
        if script:
            current_script = script
        resolved.append((current_direction, current_script))

    ranges: list[tuple[int, int, str, str]] = []
    start = 0
    for index in range(1, len(chars)):
        if resolved[index] != resolved[index - 1]:
            ranges.append((start, index, *resolved[index - 1]))
            start = index
    ranges.append((start, len(chars), *resolved[-1]))

    if len(ranges) == 1:
        segment = dict(span)
        segment["_editScript"] = ranges[0][3]
        return [(0, segment, ranges[0][2])]

    result: list[tuple[int, dict[str, Any], str]] = []
    for segment_index, (start, end, direction, script) in enumerate(ranges):
        segment_chars = chars[start:end]
        bboxes = [char.get("bbox", [0, 0, 0, 0]) for char in segment_chars]
        bbox = [
            min(box[0] for box in bboxes),
            min(box[1] for box in bboxes),
            max(box[2] for box in bboxes),
            max(box[3] for box in bboxes),
        ]
        segment = dict(span)
        segment["chars"] = segment_chars
        segment["bbox"] = bbox
        origin = list(span.get("origin", [bbox[0], bbox[3]]))
        segment["origin"] = [bbox[0], origin[1]]
        segment["_editScript"] = script
        result.append((segment_index, segment, direction))
    return result
