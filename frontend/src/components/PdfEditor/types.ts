export type ElementType = "text" | "image";
export type FontFamily = "helvetica" | "times" | "courier";

// ── Editor mode ──────────────────────────────────────────────────────────────
// "annotate"  – drag-and-drop overlay tool (text boxes, stamps, signatures)
// "text-edit" – click existing PDF text to edit it in place
export type EditorMode = "annotate" | "text-edit";

// ── In-place text editing ────────────────────────────────────────────────────

/** A line of existing PDF text detected by pdfjs-dist, with both
 *  canvas-pixel coordinates (for overlay positioning) and PDF-point
 *  coordinates (sent to the backend for redact + reinsert). */
export interface PdfTextSpan {
  id: string;
  page: number;         // 1-indexed
  text: string;
  // Canvas-pixel bounding box — used to position the overlay div
  canvasX: number;
  canvasY: number;
  canvasWidth: number;
  canvasHeight: number;
  // PDF-point bounding box — sent to the backend for redact+reinsert
  pdfX0: number;
  pdfY0: number;
  pdfX1: number;
  pdfY1: number;
  // PDF-point baseline Y (y-up coordinate system).
  // Sent to the backend so insert_text() can place the new text at exactly
  // the same vertical position as the original without the padded-rect heuristic.
  pdfBaselineY: number;
  fontSizePx: number;   // estimated canvas-pixel font size, for display only
  // True when the text has non-trivial rotation (|b| in transform matrix > 0.1).
  // Rotated spans are shown with a ⊗ cursor and cannot be edited in-place.
  isRotated: boolean;
}

export interface EditorElement {
  id: string;
  page: number;
  type: ElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  // Text element properties
  text?: string;
  fontSize?: number;       // canvas pixels (divided by PDF_RENDER_SCALE before sending to backend)
  fontFamily?: FontFamily;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  color?: string;
  // Image element properties
  imageDataUrl?: string;
}

export interface PageSize {
  width: number;
  height: number;
}
