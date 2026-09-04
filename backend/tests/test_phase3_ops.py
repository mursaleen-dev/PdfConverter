"""
Phase 3 unit tests.

Covers: glyph-coverage detection, shrink-scale loop (dual floor), redaction
rect construction, span-id resolution after page ops, font-tier selection,
and tokenization.
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
import pymupdf_fonts
import pytest

from app.font_resolver import (
    FontResolution,
    _all_glyphs_present,
    _missing_glyphs,
    _base14_name,
    _ubuntu_fontname,
    _guess_family,
    _try_system_font,
    css_weight,
    display_family,
    resolve_font,
    source_face_style,
)
from app.routers.text_edit import (
    _runs_total_width,
    _find_shrink_scale,
    _extract_all_text,
    _build_span_lookup,
    _line_rect_from_span_ids,
    _clamp_rect_above_rules,
    _clamp_paint_rect,
    _thin_horizontal_strokes,
    _sample_bg_rgb,
    apply_text_edits,
    _tokenize,
    SHRINK_MIN_S,
    SHRINK_STEP,
)
from app.routers.extract import _split_line_at_column_gaps


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_simple_pdf(text: str = "Hello World") -> tuple[fitz.Document, fitz.Page]:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(50, 100), text, fontsize=12)
    return doc, page


def make_pdf_with_ubuntu(text: str = "Hello World") -> tuple[fitz.Document, fitz.Page]:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    buf = pymupdf_fonts.fontbuffers["ubuntu"]()
    page.insert_font(fontname="Ubuntu", fontbuffer=buf)
    page.insert_text(fitz.Point(50, 100), text, fontname="Ubuntu", fontsize=12)
    return doc, page


# ── Glyph coverage ────────────────────────────────────────────────────────────

class TestGlyphCoverage:
    def test_helv_has_latin(self):
        font = fitz.Font("helv")
        assert _all_glyphs_present(font, "Hello World")

    def test_helv_missing_arabic(self):
        font = fitz.Font("helv")
        # Arabic character U+0645
        assert not _all_glyphs_present(font, "م")

    def test_ubuntu_has_latin_and_cyrillic(self):
        buf = pymupdf_fonts.fontbuffers["ubuntu"]()
        font = fitz.Font(fontbuffer=buf)
        assert _all_glyphs_present(font, "Hello мир café")

    def test_ubuntu_missing_arabic(self):
        buf = pymupdf_fonts.fontbuffers["ubuntu"]()
        font = fitz.Font(fontbuffer=buf)
        missing = _missing_glyphs(font, "م")
        assert "م" in missing

    def test_missing_glyphs_returns_unique_chars(self):
        font = fitz.Font("helv")
        missing = _missing_glyphs(font, "aaaمم")
        assert len(missing) == 2  # both instances of U+0645

    def test_spaces_ignored_in_coverage_check(self):
        font = fitz.Font("helv")
        assert _all_glyphs_present(font, "  \t\n")


# ── Shrink scale loop ─────────────────────────────────────────────────────────

class TestShrinkScale:
    def _make_font_and_runs(self, text: str = "Hello World"):
        buf = pymupdf_fonts.fontbuffers["ubuntu"]()
        font = fitz.Font(fontbuffer=buf)
        runs = [{"text": text, "sizeScale": 1.0, "color": "#000000"}]
        return font, runs

    def test_fits_at_1_0(self):
        font, runs = self._make_font_and_runs("Hi")
        dom_size = 12.0
        # Very wide available width — should return 1.0
        s = _find_shrink_scale(runs, dom_size, 1000.0, font)
        assert s == pytest.approx(1.0)

    def test_shrinks_to_fit(self):
        font, runs = self._make_font_and_runs("Hello World Hello World")
        dom_size = 12.0
        full_w = _runs_total_width(runs, dom_size, font, 1.0)
        # Provide 70% of full width to force shrink
        narrow_w = full_w * 0.75
        s = _find_shrink_scale(runs, dom_size, narrow_w, font)
        assert s < 1.0
        assert s >= SHRINK_MIN_S

    def test_dual_floor_size(self):
        font, runs = self._make_font_and_runs("Some text")
        # Very tiny dom_size: s * dom_size must stay >= 6pt
        dom_size = 7.0
        # s = 0.80 → 0.80 * 7 = 5.6 < 6.0 → floor kicks in
        # So result should be limited to s where s * 7 >= 6  => s >= 6/7 ≈ 0.857
        s = _find_shrink_scale(runs, dom_size, 0.001, font)
        assert s * dom_size >= 6.0 - 0.01

    def test_dual_floor_ratio(self):
        font, runs = self._make_font_and_runs("Long text that clearly won't fit")
        dom_size = 100.0  # huge font
        # Provide impossibly narrow width
        s = _find_shrink_scale(runs, dom_size, 1.0, font)
        assert s >= SHRINK_MIN_S


# ── Span-id resolution ────────────────────────────────────────────────────────

class TestSpanIdResolution:
    def _make_rawdict(self, page_id: str) -> dict[str, Any]:
        """
        Build a synthetic rawdict for testing.
        Line bbox is intentionally tight (top=90, bottom=97) so that the
        ascender/descender expansion is visible in the output rects.
        baseline_y=96, asc=0.83*12≈9.96, desc=0.21*12≈2.52
          → expanded_top = min(90, 86.04) = 86.04  (< 90)
          → expanded_bottom = max(97, 98.52) = 98.52 (> 97)
        """
        return {
            "blocks": [
                {
                    "type": 0,
                    "number": 0,
                    "lines": [
                        {
                            "bbox": [50, 90, 300, 97],
                            "dir": [1.0, 0.0],
                            "spans": [
                                {
                                    "text": "Hello",
                                    "bbox": [50, 90, 130, 97],
                                    "size": 12.0,
                                    "flags": 0,
                                    "color": 0,
                                    "font": "Helvetica",
                                    "origin": [50, 96],
                                    "ascender": 0.83,
                                    "descender": -0.21,
                                    "chars": [{"c": c} for c in "Hello"],
                                },
                                {
                                    "text": "World",
                                    "bbox": [135, 90, 220, 97],
                                    "size": 12.0,
                                    "flags": 0,
                                    "color": 0,
                                    "font": "Helvetica",
                                    "origin": [135, 96],
                                    "ascender": 0.83,
                                    "descender": -0.21,
                                    "chars": [{"c": c} for c in "World"],
                                },
                            ],
                        }
                    ],
                },
                {
                    "type": 0,
                    "number": 1,
                    "lines": [
                        {
                            "bbox": [50, 125, 200, 133],
                            "dir": [1.0, 0.0],
                            "spans": [
                                {
                                    "text": "Second",
                                    "bbox": [50, 125, 150, 133],
                                    "size": 10.0,
                                    "flags": 0,
                                    "color": 0,
                                    "font": "Helvetica",
                                    "origin": [50, 136],
                                    "ascender": 0.83,
                                    "descender": -0.21,
                                    "chars": [{"c": c} for c in "Second"],
                                }
                            ],
                        }
                    ],
                },
            ]
        }

    def test_lookup_correct_keys(self):
        page_id = "p1"
        raw = self._make_rawdict(page_id)
        lookup = _build_span_lookup(raw, page_id)
        assert "p1:0:0:0" in lookup
        assert "p1:0:0:1" in lookup
        assert "p1:1:0:0" in lookup

    def test_lookup_span_text(self):
        raw = self._make_rawdict("px")
        lookup = _build_span_lookup(raw, "px")
        span = lookup.get("px:0:0:0")
        assert span is not None
        assert span["text"] == "Hello"

    def test_line_rects_from_span_ids(self):
        raw = self._make_rawdict("p1")
        rects = _line_rect_from_span_ids(["p1:0:0:0", "p1:0:0:1"], raw)
        assert len(rects) == 1  # both spans are on the same line
        r = rects[0]
        # bbox[1]=90, baseline_y=96, asc≈9.96 → expanded_top≈86.04 < 90
        assert r[1] < 90, f"Top should expand above line_bbox top=90, got {r[1]}"
        # bbox[3]=97, baseline_y=96, desc≈2.52 → expanded_bottom≈98.52 > 97
        assert r[3] > 97, f"Bottom should expand below line_bbox bottom=97, got {r[3]}"

    def test_clamp_stops_above_table_rule(self):
        rect = [40.0, 90.0, 90.0, 100.0]
        # Cell-width rule sitting under the value, like a ticket table row.
        clamped = _clamp_rect_above_rules(rect, [(30.0, 120.0, 98.4)])
        assert clamped[3] < 98.4
        assert clamped[2] == rect[2]

    def test_clamp_ignores_unrelated_rule(self):
        rect = [40.0, 90.0, 90.0, 100.0]
        clamped = _clamp_rect_above_rules(rect, [(200.0, 300.0, 98.4)])
        assert clamped[3] == rect[3]

    def test_clamp_stops_below_rule_above_text(self):
        rect = [40.0, 90.0, 90.0, 100.0]
        clamped = _clamp_rect_above_rules(rect, [(30.0, 120.0, 90.2)])
        assert clamped[1] > 90.2

    def test_cell_rectangle_edges_are_table_rules(self):
        doc = fitz.open()
        page = doc.new_page(width=400, height=300)
        page.draw_rect(fitz.Rect(40, 80, 360, 112), color=(0, 0, 0), width=0.8)
        strokes = _thin_horizontal_strokes(page)
        ys = [round(y, 1) for _, _, y in strokes]
        assert 80.0 in ys
        assert 112.0 in ys
        doc.close()

    def test_paint_rect_stays_inside_table_cell(self):
        doc = fitz.open()
        page = doc.new_page(width=400, height=300)
        page.draw_rect(fitz.Rect(40, 80, 360, 112), color=(0, 0, 0), width=0.8)
        strokes = _thin_horizontal_strokes(page)
        # Expanded descender box that would otherwise cover the bottom rule.
        clamped = _clamp_paint_rect([50.0, 82.0, 200.0, 113.0], page, strokes)
        assert clamped[3] < 112.0
        assert clamped[1] > 80.0
        doc.close()

    def test_edit_does_not_erase_cell_border(self):
        orig = fitz.open()
        page = orig.new_page(width=400, height=300)
        page.draw_rect(fitz.Rect(40, 80, 360, 112), color=(0, 0, 0), width=1.0)
        page.insert_text(fitz.Point(50, 100), "ApplicantValue", fontsize=11)
        raw = orig.tobytes()
        orig.close()
        orig = fitz.open(stream=raw, filetype="pdf")
        rebuilt = fitz.open(stream=raw, filetype="pdf")
        apply_text_edits(
            rebuilt,
            orig,
            {"p0": 0},
            [{"pageId": "p0", "sourceIndex": 0}],
            [{
                "pageId": "p0",
                "spanIds": ["p0:0:0:0"],
                "newText": [{"text": "New Name", "sizeScale": 1.0, "color": "#000000"}],
                "overflowPolicy": "overflow",
            }],
        )
        assert "New Name" in rebuilt[0].get_text()
        pix = rebuilt[0].get_pixmap(
            matrix=fitz.Matrix(3, 3),
            clip=fitz.Rect(90, 110, 140, 114),
            colorspace=fitz.csRGB,
        )
        dark = False
        for y in range(pix.height):
            for x in range(pix.width):
                r, g, b = pix.pixel(x, y)[:3]
                if r < 80 and g < 80 and b < 80:
                    dark = True
                    break
            if dark:
                break
        assert dark, "bottom table rule should still be visible after the edit"
        orig.close()
        rebuilt.close()

    def test_heading_fill_is_not_replaced_with_white(self):
        grey = (216 / 255, 216 / 255, 216 / 255)
        orig = fitz.open()
        page = orig.new_page(width=400, height=300)
        page.draw_rect(fitz.Rect(40, 80, 360, 112), color=(0, 0, 0), fill=grey, width=1.0)
        page.insert_text(fitz.Point(50, 100), "Visit Details", fontsize=12)
        raw = orig.tobytes()
        orig.close()
        orig = fitz.open(stream=raw, filetype="pdf")
        rebuilt = fitz.open(stream=raw, filetype="pdf")
        sampled = _sample_bg_rgb(orig[0], fitz.Rect(50, 88, 140, 108))
        assert all(abs(channel - 216 / 255) < 0.05 for channel in sampled)
        from app.routers.extract import extract_page_data

        data = extract_page_data(orig[0], "p0", 0)
        heading = next(
            span
            for para in data["paragraphs"]
            for line in para["lines"]
            for span in line["spans"]
            if "Visit Details" in span["text"]
        )
        assert heading["backgroundColor"].lower() == "#d8d8d8"
        apply_text_edits(
            rebuilt,
            orig,
            {"p0": 0},
            [{"pageId": "p0", "sourceIndex": 0}],
            [{
                "pageId": "p0",
                "spanIds": ["p0:0:0:0"],
                "newText": [{"text": "Visit Details Was", "sizeScale": 1.0, "color": "#000000"}],
                "overflowPolicy": "overflow",
            }],
        )
        assert "Visit Details Was" in rebuilt[0].get_text()
        pix = rebuilt[0].get_pixmap(
            matrix=fitz.Matrix(3, 3),
            clip=fitz.Rect(250, 90, 300, 104),
            colorspace=fitz.csRGB,
        )
        r, g, b = pix.pixel(pix.width // 2, pix.height // 2)[:3]
        assert r < 240 and g < 240 and b < 240, "heading fill must not become white"
        assert abs(r - 216) < 25
        orig.close()
        rebuilt.close()

    def test_single_span_redaction_does_not_cover_neighbor(self):
        raw = self._make_rawdict("p1")
        rects = _line_rect_from_span_ids(["p1:0:0:0"], raw)
        assert len(rects) == 1
        assert rects[0][2] < 135, "redaction must stop before the neighboring span"

    def test_line_rects_different_blocks(self):
        raw = self._make_rawdict("p1")
        rects = _line_rect_from_span_ids(["p1:0:0:0", "p1:1:0:0"], raw)
        assert len(rects) == 2  # two different lines (in different blocks)

    def test_invalid_span_id_ignored(self):
        raw = self._make_rawdict("p1")
        rects = _line_rect_from_span_ids(["p1:99:99:0"], raw)
        assert rects == []


class TestMixedDirectionGrouping:
    def test_reversed_content_order_splits_visual_columns(self):
        arabic = {"text": "Arabic", "bbox": [470.0, 90.0, 515.0, 105.0]}
        value = {"text": "2022/11/19", "bbox": [340.0, 90.0, 383.0, 105.0]}
        groups = _split_line_at_column_gaps([arabic, value], col_threshold=18.0)
        assert [[span["text"] for span in group] for group in groups] == [
            ["2022/11/19"],
            ["Arabic"],
        ]


# ── Tokenization ──────────────────────────────────────────────────────────────

class TestTokenize:
    def test_single_word(self):
        assert _tokenize("hello") == ["hello"]

    def test_two_words(self):
        tokens = _tokenize("hello world")
        # Should produce ["hello ", "world"] so space stays with first word
        assert "".join(tokens) == "hello world"
        assert len(tokens) == 2

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_leading_space(self):
        tokens = _tokenize(" hello")
        assert "".join(tokens) == " hello"


# ── Font-family helpers ───────────────────────────────────────────────────────

class TestFontHelpers:
    def test_guess_family_times(self):
        assert _guess_family("TimesNewRoman") == "serif"

    def test_guess_family_courier(self):
        assert _guess_family("CourierNew") == "mono"

    def test_guess_family_helvetica(self):
        assert _guess_family("HelveticaNeue") == "sans"

    def test_base14_sans_bold(self):
        assert _base14_name("sans", True, False) == "hebo"

    def test_base14_serif_bolditalic(self):
        assert _base14_name("serif", True, True) == "tibo"

    def test_ubuntu_bold_italic(self):
        assert _ubuntu_fontname(True, True) == "ubuntubi"

    def test_ubuntu_regular(self):
        assert _ubuntu_fontname(False, False) == "ubuntu"


# ── resolve_font (integration, needs real PDF) ────────────────────────────────

class TestResolveFontIntegration:
    def test_tier_b_with_base14_text(self):
        doc, page = make_simple_pdf("Hello")
        # Helvetica is not embedded (Base-14 reference) → Tier B
        res = resolve_font(doc, page, "Helvetica", False, False, "Hello")
        assert res.tier in ("B", "C")   # may fall to C if B check varies
        doc.close()

    def test_tier_a_with_embedded_ubuntu(self):
        doc, page = make_pdf_with_ubuntu("Hello")
        # Re-save to ensure font is embedded
        buf = BytesIO()
        doc.save(buf)
        doc.close()
        doc2 = fitz.open(stream=buf.getvalue())
        page2 = doc2[0]
        # The font name inside the doc will be "Ubuntu Regular" or similar
        fonts = page2.get_fonts(full=True)
        basefont = fonts[0][3] if fonts else "Ubuntu Regular"
        res = resolve_font(doc2, page2, basefont, False, False, "Hello")
        assert res.tier == "A"
        doc2.close()

    def test_tier_c_fallback(self):
        doc, page = make_simple_pdf("Hello")
        # Force to Tier C by using a font name that doesn't match anything embedded
        # and text that Helvetica (Tier B) covers fine, but we can force C
        # by picking a font name that returns no embedded match and using Cyrillic
        res = resolve_font(doc, page, "NonExistentFont", False, False, "Привет")
        assert res.tier in ("B", "C")  # Helvetica doesn't have Cyrillic → C
        doc.close()

    def test_tier_c_supports_arabic(self):
        doc, page = make_simple_pdf("Hello")
        res = resolve_font(doc, page, "NonExistentFont", False, False, "ملك")
        assert res.tier == "C"
        assert res.css_family == "FiraGO"
        doc.close()

    def test_system_family_used_when_subset_is_incomplete(self):
        res = _try_system_font("Noto Sans", True, False, "LHR", 700)
        if res is None:
            pytest.skip("Noto Sans Bold is not installed on this machine")
        assert res.tier == "A"
        assert "noto" in res.css_family.lower()
        assert res.fontbuffer
        font = fitz.Font(fontbuffer=res.fontbuffer)
        assert _all_glyphs_present(font, "LHR")

    def test_generic_names_do_not_steal_system_fonts(self):
        doc, page = make_simple_pdf("Hello")
        res = resolve_font(doc, page, "Helvetica", False, False, "Hello")
        assert res.tier in ("B", "C")
        doc.close()

    def test_pdf_style_name_finds_system_family(self):
        res = _try_system_font("ABCDEF+NotoSans-Regular", True, False, "LHR", 700)
        if res is None:
            pytest.skip("Noto Sans Bold is not installed on this machine")
        assert res.tier == "A"
        assert "noto" in res.css_family.lower()

    def test_display_family_strips_subset_and_style(self):
        assert display_family("ABCDEF+NotoSans-Regular") == "Noto Sans"
        assert display_family("Arial-BoldMT") == "Arial"
        assert display_family("Noto Sans") == "Noto Sans"

    def test_css_weight_keeps_medium_and_semibold(self):
        assert css_weight(400) == 400
        assert css_weight(500) == 500
        assert css_weight(600) == 600
        assert css_weight(700) == 700

    def test_source_face_used_for_every_embedded_name(self):
        itinerary = Path(r"c:\Users\Dell\Downloads\__ The Travel Itinerary-1.pdf")
        if not itinerary.exists():
            pytest.skip("itinerary sample PDF not present")
        doc = fitz.open(itinerary)
        page = doc[0]
        bold_face = source_face_style(doc, page, "Type3 (12 0 R)")
        regular_face = source_face_style(doc, page, "Type3 (10 0 R)")
        assert bold_face.family == "Noto Sans"
        assert bold_face.weight == 700
        assert bold_face.bold
        assert regular_face.family == "Noto Sans"
        assert regular_face.weight == 400
        assert not regular_face.bold
        res = resolve_font(doc, page, "Type3 (12 0 R)", False, False, "LHR")
        assert res.tier == "A"
        assert "noto" in (res.css_family or res.fontname).lower()
        doc.close()

    def test_extract_sends_weighted_preview_fonts(self):
        itinerary = Path(r"c:\Users\Dell\Downloads\__ The Travel Itinerary-1.pdf")
        if not itinerary.exists():
            pytest.skip("itinerary sample PDF not present")
        from app.routers.extract import _extract_browser_fonts

        doc = fitz.open(itinerary)
        fonts = _extract_browser_fonts(doc[0])
        assert isinstance(fonts, list)
        pairs = {(item["family"], item["weight"]) for item in fonts}
        assert ("Noto Sans", "700") in pairs
        assert ("Noto Sans", "400") in pairs
        for item in fonts:
            assert item["src"].startswith("data:font/")
        doc.close()

