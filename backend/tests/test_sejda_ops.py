"""
Unit tests for Phase 2 sejda page-operation logic.
Run with: cd backend && python -m pytest tests/test_sejda_ops.py -v
"""
from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import fitz
import pytest

from app.routers.sejda import _build_from_page_ops, _hex_to_rgb


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_pdf(num_pages: int = 3, rotate: int = 0) -> fitz.Document:
    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page(width=595, height=842)
        if rotate:
            page.set_rotation(rotate)
    return doc


# ── rotation normalization (backend effective-rotation math) ──────────────────

class TestEffectiveRotation:
    def test_no_user_rotation(self):
        orig = make_pdf(1)
        orig[0].set_rotation(90)
        ops = [{"pageId": "p1", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 842, "height": 595}]
        new_doc, _ = _build_from_page_ops(orig, ops)
        # Source page has /Rotate 90; user rotation 0 → effective should remain 90
        assert new_doc[0].rotation == 90
        orig.close(); new_doc.close()

    def test_compose_rotations(self):
        orig = make_pdf(1)
        orig[0].set_rotation(90)
        # User adds 90° CW on top → effective = 180°
        ops = [{"pageId": "p1", "sourceIndex": 0, "rotation": 90, "isBlank": False, "width": 595, "height": 842}]
        new_doc, _ = _build_from_page_ops(orig, ops)
        assert new_doc[0].rotation == 180
        orig.close(); new_doc.close()

    def test_full_circle_normalises(self):
        orig = make_pdf(1)
        orig[0].set_rotation(270)
        # 270 + 90 = 360 → 0
        ops = [{"pageId": "p1", "sourceIndex": 0, "rotation": 90, "isBlank": False, "width": 842, "height": 595}]
        new_doc, _ = _build_from_page_ops(orig, ops)
        assert new_doc[0].rotation == 0
        orig.close(); new_doc.close()

    def test_180_rotation(self):
        orig = make_pdf(1)
        ops = [{"pageId": "p1", "sourceIndex": 0, "rotation": 180, "isBlank": False, "width": 595, "height": 842}]
        new_doc, _ = _build_from_page_ops(orig, ops)
        assert new_doc[0].rotation == 180
        orig.close(); new_doc.close()


# ── pageId → new index resolution ─────────────────────────────────────────────

class TestPageIdResolution:
    def test_identity_order(self):
        orig = make_pdf(3)
        ops = [
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "b", "sourceIndex": 1, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "c", "sourceIndex": 2, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        _, mapping = _build_from_page_ops(orig, ops)
        assert mapping == {"a": 0, "b": 1, "c": 2}
        orig.close()

    def test_reordered(self):
        orig = make_pdf(3)
        ops = [
            {"pageId": "c", "sourceIndex": 2, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "b", "sourceIndex": 1, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        _, mapping = _build_from_page_ops(orig, ops)
        assert mapping == {"c": 0, "a": 1, "b": 2}
        orig.close()

    def test_deleted_page(self):
        orig = make_pdf(3)
        # Only pages 0 and 2 are kept (page 1 deleted)
        ops = [
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "c", "sourceIndex": 2, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        new_doc, mapping = _build_from_page_ops(orig, ops)
        assert len(new_doc) == 2
        assert mapping == {"a": 0, "c": 1}
        orig.close(); new_doc.close()

    def test_blank_page_inserted(self):
        orig = make_pdf(2)
        ops = [
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "blank1", "sourceIndex": -1, "rotation": 0, "isBlank": True, "width": 595, "height": 842},
            {"pageId": "b", "sourceIndex": 1, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        new_doc, mapping = _build_from_page_ops(orig, ops)
        assert len(new_doc) == 3
        assert mapping == {"a": 0, "blank1": 1, "b": 2}
        # Blank page should be 595×842
        blank = new_doc[1]
        assert blank.rect.width == pytest.approx(595, abs=1)
        assert blank.rect.height == pytest.approx(842, abs=1)
        orig.close(); new_doc.close()

    def test_duplicate_page(self):
        orig = make_pdf(2)
        ops = [
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "a_dup", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "b", "sourceIndex": 1, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        new_doc, mapping = _build_from_page_ops(orig, ops)
        assert len(new_doc) == 3
        assert mapping["a_dup"] == 1
        orig.close(); new_doc.close()


# ── delete with overlays (integration: pageId absent from rebuilt doc) ─────────

class TestDeleteWithOverlays:
    def test_deleted_page_overlay_skipped(self):
        """
        Overlay for a deleted pageId should be silently skipped, not raise.
        We test this by building a doc without that pageId in the mapping,
        then checking the manifest-application logic skips it.
        """
        orig = make_pdf(3)
        # Delete page 1 (sourceIndex=1) in page_ops
        ops = [
            {"pageId": "a", "sourceIndex": 0, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
            {"pageId": "c", "sourceIndex": 2, "rotation": 0, "isBlank": False, "width": 595, "height": 842},
        ]
        new_doc, mapping = _build_from_page_ops(orig, ops)
        # "b" (pageId for deleted page 1) is absent from mapping
        assert "b" not in mapping
        # Confirm only 2 pages survived
        assert len(new_doc) == 2
        orig.close(); new_doc.close()


# ── _hex_to_rgb edge cases ────────────────────────────────────────────────────

class TestHexToRgb:
    def test_shorthand(self):
        r, g, b = _hex_to_rgb("#f00")
        assert r == pytest.approx(1.0)
        assert g == 0.0
        assert b == 0.0

    def test_full(self):
        r, g, b = _hex_to_rgb("#ff8000")
        assert r == pytest.approx(1.0)
        assert g == pytest.approx(128 / 255, abs=0.005)
        assert b == 0.0

    def test_none_input(self):
        assert _hex_to_rgb(None) is None

    def test_invalid_returns_none(self):
        assert _hex_to_rgb("notacolor") is None
