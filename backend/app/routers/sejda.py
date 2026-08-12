"""
POST /api/sejda — apply a Fabric.js overlay manifest to a PDF using PyMuPDF.

Coordinate contract (mirrors frontend types.ts):
  Manifest objects store x, y, width, height in PDF points with TOP-LEFT origin,
  Y increasing downward.  PyMuPDF's normalised page coordinate space uses the
  same convention, so fitz.Rect(x, y, x+w, y+h) maps directly — no y-flip.

Phase 2 page_ops:
  Optional JSON array of PageDescriptor objects that describes the desired page
  order/rotation/blank-insertion.  When present the backend rebuilds the
  document first (insert_pdf / new_page), sets effective rotations, then applies
  overlays using the pageId → new-page-index mapping.

Font mapping:
  "helv"  → Helvetica family
  "tiro"  → Times-Roman family
  "cour"  → Courier family
"""
from __future__ import annotations

import base64
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.routers.text_edit import apply_text_edits

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_OBJECTS = 500
MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB per image
MAX_TEXT_LENGTH = 4000
MAX_FILE_MB = 50


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str | None) -> tuple[float, float, float] | None:
    """Convert "#rrggbb" to a (r, g, b) tuple with values 0–1, or None."""
    if not hex_color:
        return None
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r / 255, g / 255, b / 255)
    except ValueError:
        return None


def _base64_to_bytes(data_url: str) -> bytes:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def _resolve_font(family: str, bold: bool, italic: bool) -> str:
    """Return a PyMuPDF Base14 font name string."""
    base = family.lower()
    if "tiro" in base or "time" in base:
        if bold and italic:
            return "tibo"
        if bold:
            return "tib"
        if italic:
            return "tiit"
        return "tiro"
    if "cour" in base:
        if bold and italic:
            return "cobi"
        if bold:
            return "cob"
        if italic:
            return "coit"
        return "cour"
    # Default: Helvetica
    if bold and italic:
        return "helbi"
    if bold:
        return "heb"
    if italic:
        return "heit"
    return "helv"


def _apply_text(page: fitz.Page, obj: dict[str, Any]) -> None:
    x, y = obj["x"], obj["y"]
    w, h = obj["width"], obj["height"]
    rect = fitz.Rect(x, y, x + w, y + h)

    text = (obj.get("text") or "").strip()
    if not text:
        return

    font_name = _resolve_font(
        obj.get("fontFamily", "helv"),
        bool(obj.get("bold")),
        bool(obj.get("italic")),
    )
    font_size = float(obj.get("fontSize") or 12)
    color = _hex_to_rgb(obj.get("color")) or (0, 0, 0)
    rotation = float(obj.get("rotation") or 0)

    page.insert_textbox(
        rect,
        text,
        fontsize=font_size,
        fontname=font_name,
        color=color,
        align=fitz.TEXT_ALIGN_LEFT,
        rotate=int(-rotation),
    )

    if obj.get("underline"):
        y_line = y + font_size + 2
        shape = page.new_shape()
        shape.draw_line(fitz.Point(x, y_line), fitz.Point(x + w, y_line))
        shape.finish(color=color, width=max(0.5, font_size * 0.06))
        shape.commit()


def _apply_image(page: fitz.Page, obj: dict[str, Any]) -> None:
    x, y = obj["x"], obj["y"]
    w, h = obj["width"], obj["height"]
    rect = fitz.Rect(x, y, x + w, y + h)

    img_data = obj.get("imageData") or ""
    if not img_data:
        return
    img_bytes = _base64_to_bytes(img_data)
    if len(img_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB).")

    rotation = float(obj.get("rotation") or 0)
    page.insert_image(rect, stream=img_bytes, rotate=int(rotation))


def _apply_rect(page: fitz.Page, obj: dict[str, Any]) -> None:
    x, y = obj["x"], obj["y"]
    w, h = obj["width"], obj["height"]
    rect = fitz.Rect(x, y, x + w, y + h)

    obj_type = obj["type"]
    fill_color = _hex_to_rgb(obj.get("fillColor"))
    stroke_color = _hex_to_rgb(obj.get("strokeColor"))
    stroke_width = float(obj.get("strokeWidth") or 1)
    fill_opacity = float(obj.get("fillOpacity") or 1.0)

    if obj_type == "whiteout":
        fill_color = (1.0, 1.0, 1.0)
        stroke_color = (1.0, 1.0, 1.0)
        stroke_width = 0
        fill_opacity = 1.0
    elif obj_type == "highlight":
        fill_color = fill_color or (0.98, 0.8, 0.08)
        stroke_color = None
        fill_opacity = fill_opacity if fill_opacity < 1 else 0.4
    elif obj_type == "strikethrough":
        cy = y + h / 2
        shape = page.new_shape()
        shape.draw_line(fitz.Point(x, cy), fitz.Point(x + w, cy))
        shape.finish(color=stroke_color or (0, 0, 0), width=max(0.5, stroke_width))
        shape.commit()
        return

    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(
        color=stroke_color,
        fill=fill_color,
        fill_opacity=fill_opacity,
        width=stroke_width if stroke_color else 0,
    )
    shape.commit()


def _apply_ellipse(page: fitz.Page, obj: dict[str, Any]) -> None:
    x, y = obj["x"], obj["y"]
    w, h = obj["width"], obj["height"]
    rect = fitz.Rect(x, y, x + w, y + h)

    fill_color = _hex_to_rgb(obj.get("fillColor"))
    stroke_color = _hex_to_rgb(obj.get("strokeColor"))
    stroke_width = float(obj.get("strokeWidth") or 1)
    fill_opacity = float(obj.get("fillOpacity") or 1.0)

    shape = page.new_shape()
    shape.draw_oval(rect)
    shape.finish(
        color=stroke_color,
        fill=fill_color,
        fill_opacity=fill_opacity,
        width=stroke_width if stroke_color else 0,
    )
    shape.commit()


def _apply_freehand(page: fitz.Page, obj: dict[str, Any]) -> None:
    raw_pts = obj.get("points") or []
    if len(raw_pts) < 2:
        return

    pts = [fitz.Point(p["x"], p["y"]) for p in raw_pts]
    stroke_color = _hex_to_rgb(obj.get("strokeColor")) or (0, 0, 0)
    stroke_width = float(obj.get("strokeWidth") or 2)

    shape = page.new_shape()
    shape.draw_polyline(pts)
    shape.finish(color=stroke_color, fill=None, width=stroke_width)
    shape.commit()


def _build_from_page_ops(
    orig_doc: fitz.Document,
    page_ops: list[dict[str, Any]],
) -> tuple[fitz.Document, dict[str, int]]:
    """
    Rebuild a new fitz.Document from page_ops descriptors.
    Returns (new_doc, page_id_to_new_index).

    Each op:
      pageId: str
      sourceIndex: int   (-1 for blank)
      rotation: int      user-applied CW rotation (0/90/180/270)
      isBlank: bool
      width: float       post-rotation width in PDF points
      height: float      post-rotation height in PDF points
    """
    new_doc = fitz.open()
    page_id_map: dict[str, int] = {}

    for new_idx, op in enumerate(page_ops):
        page_id = op.get("pageId", "")
        is_blank = bool(op.get("isBlank", False))

        if is_blank:
            w = float(op.get("width", 595))
            h = float(op.get("height", 842))
            new_doc.new_page(width=w, height=h)
        else:
            src_idx = int(op.get("sourceIndex", 0))
            if src_idx < 0 or src_idx >= len(orig_doc):
                # Out-of-range source — insert blank of same size
                w = float(op.get("width", 595))
                h = float(op.get("height", 842))
                new_doc.new_page(width=w, height=h)
            else:
                new_doc.insert_pdf(
                    orig_doc,
                    from_page=src_idx,
                    to_page=src_idx,
                )

            # Apply effective rotation.
            # After insert_pdf the new page inherits the source /Rotate.
            # We need effective = (source_rotate + user_rotation) % 360.
            user_rotation = int(op.get("rotation", 0))
            if not is_blank and user_rotation != 0:
                src_page = orig_doc[src_idx] if 0 <= src_idx < len(orig_doc) else None
                src_rotation = src_page.rotation if src_page else 0
                effective = (src_rotation + user_rotation) % 360
                # Only call set_rotation if it differs from what was inherited
                new_page = new_doc[new_idx]
                if new_page.rotation != effective:
                    new_page.set_rotation(effective)

        if page_id:
            page_id_map[page_id] = new_idx

    return new_doc, page_id_map


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/api/sejda")
async def apply_manifest(
    file: UploadFile = File(...),
    manifest: str = Form(...),
    page_ops: str | None = Form(None),
    text_edits: str | None = Form(None),
) -> Response:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")

    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_MB} MB limit.")

    try:
        objects: list[dict[str, Any]] = json.loads(manifest)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid manifest JSON.")

    if not isinstance(objects, list):
        raise HTTPException(status_code=422, detail="Manifest must be a JSON array.")
    if len(objects) > MAX_OBJECTS:
        raise HTTPException(status_code=422, detail=f"Too many objects (max {MAX_OBJECTS}).")

    for i, obj in enumerate(objects):
        if not isinstance(obj, dict):
            raise HTTPException(status_code=422, detail=f"Object {i} is not a dict.")
        if "type" not in obj:
            raise HTTPException(status_code=422, detail=f"Object {i} missing type.")
        if "pageId" not in obj and "pageIndex" not in obj:
            raise HTTPException(status_code=422, detail=f"Object {i} missing pageId.")
        text = obj.get("text", "")
        if text and len(text) > MAX_TEXT_LENGTH:
            raise HTTPException(status_code=422, detail=f"Text in object {i} exceeds {MAX_TEXT_LENGTH} chars.")

    try:
        orig_doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse the PDF file.")

    # ── Phase 2: rebuild document from page_ops ───────────────────────────────
    ops_list: list[dict[str, Any]] | None = None
    if page_ops:
        try:
            ops_list = json.loads(page_ops)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid page_ops JSON.")

    text_edits_list: list[dict[str, Any]] | None = None
    if text_edits:
        try:
            text_edits_list = json.loads(text_edits)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid text_edits JSON.")

    if ops_list is not None:
        doc, page_id_map = _build_from_page_ops(orig_doc, ops_list)
        # Keep orig_doc open until after text edits (needed for rawdict extraction)
        num_pages = len(doc)
    else:
        # Phase 1 fallback: operate directly on original document
        doc = orig_doc
        orig_doc = None  # signal that we must not close it separately
        page_id_map = {}
        num_pages = len(doc)

    # ── Step 4: apply text edits (Phase 3) ───────────────────────────────────
    text_edit_warnings: list[str] = []
    if text_edits_list and ops_list is not None and orig_doc is not None:
        try:
            text_edit_warnings = apply_text_edits(doc, orig_doc, page_id_map, ops_list, text_edits_list)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Text edit pipeline failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Text edit failed: {exc}")

    if orig_doc is not None:
        orig_doc.close()

    # ── Apply manifest objects ────────────────────────────────────────────────
    obj_warnings: list[str] = []
    for i, obj in enumerate(objects):
        # Resolve page index
        if "pageId" in obj and page_id_map:
            page_idx = page_id_map.get(obj["pageId"])
            if page_idx is None:
                obj_warnings.append(f"Object {i} ({obj.get('type','?')}): pageId not in rebuilt doc — skipped.")
                continue
        elif "pageId" in obj and ops_list is None:
            obj_warnings.append(f"Object {i} ({obj.get('type','?')}): pageId without page_ops — skipped.")
            continue
        else:
            page_idx = int(obj.get("pageIndex", 0))

        if page_idx < 0 or page_idx >= num_pages:
            obj_warnings.append(f"Object {i} ({obj.get('type','?')}): page index {page_idx} out of range — skipped.")
            continue

        page = doc[page_idx]
        obj_type: str = obj.get("type", "")

        try:
            if obj_type == "text":
                _apply_text(page, obj)
            elif obj_type in ("image", "signature"):
                _apply_image(page, obj)
            elif obj_type in ("rect", "whiteout", "highlight", "strikethrough"):
                _apply_rect(page, obj)
            elif obj_type == "ellipse":
                _apply_ellipse(page, obj)
            elif obj_type == "freehand":
                _apply_freehand(page, obj)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Skipping manifest object %d (type=%s, page=%s): %s", i, obj_type, page_idx, exc)
            obj_warnings.append(f"Object {i} ({obj_type}) on page {page_idx} skipped: {exc}")

    buf = BytesIO()
    doc.save(buf, garbage=4, deflate=True, clean=True)
    doc.close()

    stem = Path(file.filename or "document").stem
    output_name = f"{stem}-edited.pdf"

    all_warnings = text_edit_warnings + obj_warnings
    headers: dict[str, str] = {
        "Content-Disposition": f"attachment; filename*=utf-8''{output_name}",
        "Content-Length": str(buf.tell()),
    }
    if all_warnings:
        headers["X-Sejda-Warnings"] = json.dumps(all_warnings)
        logger.warning("Export completed with %d warnings: %s", len(all_warnings), all_warnings)

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers=headers,
    )
