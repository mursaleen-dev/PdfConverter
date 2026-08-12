/**
 * Coordinate contract
 * -------------------
 * All manifest objects use PDF points with TOP-LEFT origin, Y-DOWN.
 * This matches PyMuPDF's normalised coordinate space directly — no y-flip needed
 * on the backend. The frontend converts canvas pixels → PDF points by dividing by
 * the render scale (PDF_RENDER_SCALE = 1.4).
 *
 * Backend rect construction: fitz.Rect(x, y, x+width, y+height)
 */

export type PageRotation = 0 | 90 | 180 | 270;

export interface PageDescriptor {
  pageId: string;
  sourceIndex: number;   // index in the original PDF; -1 for blank pages
  rotation: PageRotation; // user-applied rotation (cumulative, absolute degrees CW)
  isBlank: boolean;
  width: number;         // post-rotation width in PDF points
  height: number;        // post-rotation height in PDF points
}

export type ManifestObjectType =
  | "text"
  | "image"
  | "signature"
  | "rect"
  | "ellipse"
  | "freehand"
  | "highlight"
  | "strikethrough"
  | "whiteout";

export interface ManifestObject {
  type: ManifestObjectType;
  pageId: string; // stable identity across reorder/delete

  // Bounding box in PDF points, top-left origin, y-down
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number; // object's own rotation, degrees clockwise

  // Text
  text?: string;
  fontSize?: number;    // PDF points
  fontFamily?: string;  // "helv" | "tiro" | "cour"
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  color?: string;       // "#rrggbb"

  // Shapes
  strokeColor?: string;  // "#rrggbb" or undefined
  strokeWidth?: number;  // PDF points
  fillColor?: string;    // "#rrggbb" or undefined
  fillOpacity?: number;  // 0–1

  // Image / signature: base64 PNG data URL
  imageData?: string;

  // Freehand polyline: sampled canvas points (PDF points, y-down)
  points?: { x: number; y: number }[];
}

export type ActiveTool =
  | "select"
  | "text"
  | "image"
  | "signature"
  | "rect"
  | "ellipse"
  | "freehand"
  | "highlight"
  | "strikethrough"
  | "whiteout"
  | "eraser"
  | "edit-text";

// ── Phase 3: text extraction ──────────────────────────────────────────────────

export interface ExtractedSpan {
  spanId: string;
  text: string;
  bbox: [number, number, number, number]; // [x0, y0, x1, y1] in PDF pts (y-down)
  size: number;            // font size in PDF points
  bold: boolean;
  italic: boolean;
  color: string;           // "#rrggbb"
  backgroundColor: string; // estimated local PDF background behind the span
  fontName: string;        // original embedded font name
  dir: [number, number];   // text direction vector
  isLtr: boolean;
  baselineY: number;       // baseline in PDF points (y-down)
  ascenderPt: number;
  descenderPt: number;
}

export interface ExtractedLine {
  spans: ExtractedSpan[];
  bbox: [number, number, number, number];
  baselineY: number;
}

export interface ExtractedParagraph {
  paraId: string;
  lines: ExtractedLine[];
  bbox: [number, number, number, number];
  spanIds: string[];  // all spanIds within this paragraph
}

export interface ExtractedPage {
  pageId: string;
  sourceIndex: number;
  width: number;
  height: number;
  scanned: boolean;
  paragraphs: ExtractedParagraph[];
}

// ── Phase 3: text edits ───────────────────────────────────────────────────────

export type OverflowPolicy = "shrink" | "overflow" | "truncate";

export interface TextRun {
  text: string;
  bold: boolean;
  italic: boolean;
  sizeScale: number;  // 1.0 = original span's dom_size
  color: string;      // "#rrggbb"
}

export interface TextEditEntry {
  type: "textEdit";
  pageId: string;
  spanIds: string[];
  newText: TextRun[];
  overflowPolicy: OverflowPolicy;
  scaleFactorApplied?: number;  // returned by preflight; informational
}

export interface PreflightResult {
  tier: "A" | "B" | "C" | "error";
  scale_factor: number | null;
  fits: boolean;
  warning: string;
}

export interface SearchMatch {
  pageSourceIndex: number;
  pageId: string;
  bbox: [number, number, number, number];
  matchText: string;
}

export interface ToolSettings {
  fontSize: number;
  fontFamily: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  textColor: string;
  strokeColor: string;
  strokeWidth: number;
  fillColor: string;
  freehandColor: string;
  freehandWidth: number;
  opacity: number;
}

export const DEFAULT_TOOL_SETTINGS: ToolSettings = {
  fontSize: 16,
  fontFamily: "Helvetica",
  bold: false,
  italic: false,
  underline: false,
  textColor: "#111111",
  strokeColor: "#1e40af",
  strokeWidth: 2,
  fillColor: "transparent",
  freehandColor: "#111111",
  freehandWidth: 3,
  opacity: 1,
};
