import * as pdfjsLib from "pdfjs-dist";
import type { PDFPageProxy } from "pdfjs-dist";
import { PDF_RENDER_SCALE } from "./pdfRender";
import type { PdfTextSpan } from "@/components/PdfEditor/types";

export type { PdfTextSpan };

const ASCENDER_RATIO  = 0.80;
const DESCENDER_RATIO = 0.20;
const ROTATION_THRESHOLD = 0.05;

// A gap between consecutive items larger than this multiple of the font size
// is treated as a column / field separator — the items become distinct spans.
// Normal word spaces within a field are 0.2–0.4× the font size; column gaps
// in tables are typically ≥ 2×, so 1.0× is a clean split point.
const COLUMN_GAP_FACTOR = 1.0;

type RawItem = {
  str:       string;
  transform: number[];
  width:     number;    // advance width in PDF user-space units
  height:    number;
  fontName:  string;
};

/**
 * Extract text on `page` as individual PdfTextSpan objects — one per
 * discrete text run (word group / table cell), not one per visual line.
 *
 * Algorithm
 * ---------
 * 1. Bucket items by quantised baseline-Y (6 pt bucket).
 * 2. Merge adjacent buckets that fall within the same logical line
 *    (tolerance scales with the dominant font size so large headings merge
 *    correctly without over-merging body text).
 * 3. Within each merged line, cluster items by horizontal proximity:
 *    a gap larger than COLUMN_GAP_FACTOR × fontSize starts a new cluster.
 *    This keeps words within a phrase together while splitting table columns
 *    into separate, independently-editable spans.
 * 4. Each cluster → one PdfTextSpan with its own tight bounding box and
 *    PDF-space baseline Y for pixel-accurate backend reinsertion.
 */
export async function extractPageTextSpans(
  page: PDFPageProxy,
  pageNumber: number
): Promise<PdfTextSpan[]> {
  const viewport = page.getViewport({ scale: PDF_RENDER_SCALE });
  const content  = await page.getTextContent();

  // ── Step 1: bucket items by quantised baseline-Y ──────────────────────────
  const BUCKET_SIZE = 6;
  const buckets = new Map<number, RawItem[]>();

  for (const raw of content.items) {
    if (!("str" in raw)) continue;                       // skip TextMarkedContent
    const item = raw as RawItem;
    if (!item.str.trim()) continue;                      // skip whitespace-only

    // Type3 fonts (and some other fonts) report zero advance widths.  Rather
    // than discarding these items (which produces tiny, un-clickable bounding
    // boxes), fall back to a 0.6× font-size-per-character heuristic so the
    // item still participates in clustering with a reasonable right-edge estimate.
    if (item.width <= 0) {
      const [a, b] = item.transform;
      const fontSize = Math.hypot(a, b);
      if (fontSize <= 0) continue;                       // genuinely degenerate
      item.width = fontSize * 0.6 * item.str.length;
    }

    const baselineY = item.transform[5];
    const key = Math.round(baselineY / BUCKET_SIZE) * BUCKET_SIZE;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(item);
    else buckets.set(key, [item]);
  }

  // ── Step 2: merge adjacent buckets into logical lines ─────────────────────
  // Sort descending (largest PDF-y = top of page first).
  const sortedKeys = Array.from(buckets.keys()).sort((a, b) => b - a);
  const mergedLines: RawItem[][] = [];

  for (const key of sortedKeys) {
    const group = buckets.get(key)!;
    const [a, b] = group[0].transform;
    const dominantSize = Math.hypot(a, b);
    const tolerance = Math.max(dominantSize * 0.40, BUCKET_SIZE);

    const last = mergedLines[mergedLines.length - 1];
    if (last) {
      const lastKey = last[0].transform[5];
      if (Math.abs(lastKey - key) <= tolerance) {
        last.push(...group);
        continue;
      }
    }
    mergedLines.push([...group]);
  }

  // ── Step 3: within each line, cluster items by horizontal proximity ────────
  const spans: PdfTextSpan[] = [];
  let index = 0;

  for (const lineItems of mergedLines) {
    // Sort left-to-right by x origin.
    lineItems.sort((a, b) => a.transform[4] - b.transform[4]);

    // Split into clusters.  A new cluster begins when the gap between the
    // right edge of the previous item and the left edge of the current one
    // exceeds COLUMN_GAP_FACTOR × the current item's font size.
    // Right edge of item = transform[4] (x-origin) + width (advance).
    const clusters: RawItem[][] = [];
    let cur: RawItem[] = [];

    for (const item of lineItems) {
      if (cur.length === 0) {
        cur.push(item);
        continue;
      }
      const prev      = cur[cur.length - 1];
      const prevRight = prev.transform[4] + prev.width;
      const [ia, ib]  = item.transform;
      const fontSize  = Math.hypot(ia, ib);
      const gap       = item.transform[4] - prevRight;

      if (gap > fontSize * COLUMN_GAP_FACTOR) {
        clusters.push(cur);
        cur = [item];
      } else {
        cur.push(item);
      }
    }
    if (cur.length > 0) clusters.push(cur);

    // ── Step 4: convert each cluster to a PdfTextSpan ─────────────────────
    for (const items of clusters) {
      const text = items.map((i) => i.str).join("").trim();
      if (!text) continue;

      const isRotated   = items.some((i) => Math.abs(i.transform[1]) > ROTATION_THRESHOLD);
      const pdfBaselineY = items[0].transform[5];

      let pdfX0 = Infinity, pdfX1 = -Infinity;
      let pdfY0 = Infinity, pdfY1 = -Infinity;
      let maxFontSize = 0;

      for (const { transform: [a, b, , , e, f], width, height } of items) {
        const fontSize = Math.hypot(a, b);
        maxFontSize = Math.max(maxFontSize, fontSize);

        pdfX0 = Math.min(pdfX0, e);
        pdfX1 = Math.max(pdfX1, e + width);

        const lineHeight = height > 0 ? height : fontSize;
        pdfY0 = Math.min(pdfY0, f - lineHeight * DESCENDER_RATIO);
        pdfY1 = Math.max(pdfY1, f + lineHeight * ASCENDER_RATIO);
      }

      // Convert PDF y-up corners to canvas-pixel coordinates.
      const topLeft  = [pdfX0, pdfY1];
      const botRight = [pdfX1, pdfY0];
      pdfjsLib.Util.applyTransform(topLeft,  viewport.transform);
      pdfjsLib.Util.applyTransform(botRight, viewport.transform);
      const [cx0, cy0] = topLeft;
      const [cx1, cy1] = botRight;

      spans.push({
        id:           `pg${pageNumber}-${index++}`,
        page:         pageNumber,
        text,
        canvasX:      Math.min(cx0, cx1),
        canvasY:      Math.min(cy0, cy1),
        canvasWidth:  Math.abs(cx1 - cx0),
        canvasHeight: Math.abs(cy1 - cy0),
        pdfX0,
        pdfY0,
        pdfX1,
        pdfY1,
        pdfBaselineY,
        fontSizePx:   maxFontSize * PDF_RENDER_SCALE,
        isRotated,
      });
    }
  }

  // Return spans sorted top-to-bottom, left-to-right (reading order).
  return spans.sort((a, b) => a.canvasY - b.canvasY || a.canvasX - b.canvasX);
}
