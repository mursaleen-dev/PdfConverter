"""
Per-page PDF classifier: digital / scanned / mixed.

Decision rules
--------------
digital  — enough selectable text (≥ SCANNED_CHAR_THRESHOLD non-ws chars)
           AND image coverage is low (< MIXED_IMAGE_THRESHOLD).
scanned  — very little selectable text (< SCANNED_CHAR_THRESHOLD).
mixed    — some text but large raster area (≥ MIXED_IMAGE_THRESHOLD),
           OR moderate text count with high image coverage.

Only images that cover at least LARGE_IMAGE_MIN_FRAC of the page area count
toward image_coverage — small decorative icons and logos are ignored.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tuning constants                                                             #
# --------------------------------------------------------------------------- #

# Fewer non-whitespace characters than this → treat page as scanned.
_SCANNED_CHAR_THRESHOLD = 50

# An image must cover at least this fraction of page area to count.
_LARGE_IMAGE_MIN_FRAC = 0.04

# If image coverage ≥ this AND char count < MIXED_CHAR_LIMIT → mixed.
_MIXED_IMAGE_THRESHOLD = 0.30

# Char count ceiling for the mixed classification.
_MIXED_CHAR_LIMIT = 400

PageClass = Literal["digital", "scanned", "mixed"]


# --------------------------------------------------------------------------- #
# Public types                                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class PageInfo:
    """Classification result for one PDF page (0-indexed page_num)."""
    page_num: int
    classification: PageClass
    char_count: int        # non-whitespace characters found via PyMuPDF
    text_coverage: float   # fraction of page area covered by text blocks
    image_coverage: float  # fraction covered by large raster/vector images


# --------------------------------------------------------------------------- #
# Implementation                                                               #
# --------------------------------------------------------------------------- #

def classify_page(page: fitz.Page, page_num: int) -> PageInfo:
    """Classify a single fitz.Page."""
    page_w = page.rect.width
    page_h = page.rect.height
    page_area = page_w * page_h

    if page_area <= 0:
        return PageInfo(page_num, "digital", 0, 0.0, 0.0)

    # get_text("blocks") → list of (x0, y0, x1, y1, text, block_no, block_type)
    # block_type 0 = text, 1 = image
    blocks = page.get_text("blocks", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    text_blocks = [b for b in blocks if b[6] == 0]
    image_blocks = [b for b in blocks if b[6] == 1]

    # Non-whitespace character count
    char_count = sum(
        sum(1 for c in b[4] if not c.isspace())
        for b in text_blocks
    )

    # Text area (blocks with at least a few visible characters)
    text_area = sum(
        max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        for b in text_blocks
        if b[4].strip()
    )
    text_coverage = round(min(1.0, text_area / page_area), 4)

    # Image area — only images large enough to be meaningful
    min_img_area = _LARGE_IMAGE_MIN_FRAC * page_area
    large_img_area = sum(
        max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        for b in image_blocks
        if max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) >= min_img_area
    )
    image_coverage = round(min(1.0, large_img_area / page_area), 4)

    # Classification decision
    if char_count < _SCANNED_CHAR_THRESHOLD:
        cls: PageClass = "scanned"
    elif image_coverage >= _MIXED_IMAGE_THRESHOLD and char_count < _MIXED_CHAR_LIMIT:
        cls = "mixed"
    else:
        cls = "digital"

    logger.debug(
        "Page %d: class=%s chars=%d text_cov=%.3f img_cov=%.3f",
        page_num, cls, char_count, text_coverage, image_coverage,
    )
    return PageInfo(
        page_num=page_num,
        classification=cls,
        char_count=char_count,
        text_coverage=text_coverage,
        image_coverage=image_coverage,
    )


def classify_document(doc: fitz.Document) -> list[PageInfo]:
    """Classify all pages of an open fitz.Document."""
    return [classify_page(doc[i], i) for i in range(doc.page_count)]
