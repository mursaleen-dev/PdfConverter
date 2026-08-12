import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageDescriptor, PageRotation } from "./types";

export function normalizeRotation(r: number): PageRotation {
  const n = ((r % 360) + 360) % 360;
  if (n === 90) return 90;
  if (n === 180) return 180;
  if (n === 270) return 270;
  return 0;
}

export function makePageId(prefix = "p"): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

export async function buildPageDescriptors(
  pdfDoc: PDFDocumentProxy
): Promise<PageDescriptor[]> {
  const result = new Array<PageDescriptor>(pdfDoc.numPages);
  const fallback = { width: 595, height: 842 };
  let nextIndex = 0;

  // Bounded concurrency avoids the very slow sequential load on long PDFs
  // without requesting every page at once and exhausting browser memory.
  const worker = async () => {
    while (nextIndex < pdfDoc.numPages) {
      const i = nextIndex++;
      let dimensions = fallback;
      try {
        const page = await pdfDoc.getPage(i + 1);
        const viewport = page.getViewport({ scale: 1, rotation: 0 });
        dimensions = { width: viewport.width, height: viewport.height };
        page.cleanup();
      } catch {
        // Keep the page navigable; the main viewer will expose a retry action.
      }
      result[i] = {
        pageId: makePageId("orig"),
        sourceIndex: i,
        rotation: 0,
        isBlank: false,
        ...dimensions,
      };
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(4, pdfDoc.numPages) }, () => worker())
  );
  return result;
}

/** Returns the effective display dimensions for a page descriptor. */
export function effectiveDims(p: PageDescriptor): { width: number; height: number } {
  return { width: p.width, height: p.height };
}

/** Dimensions for a new blank page: neighbor's post-rotation dims, A4 fallback. */
export function blankPageDims(
  pages: PageDescriptor[],
  insertAfterIdx: number
): { width: number; height: number } {
  const neighbor = pages[insertAfterIdx] ?? pages[insertAfterIdx + 1];
  return neighbor
    ? { width: neighbor.width, height: neighbor.height }
    : { width: 595, height: 842 };
}

/**
 * Transform Fabric canvas overlay coordinates when a page is rotated by deltaRot degrees CW.
 * Keeps placed objects visually anchored to the same page content after rotation.
 *
 * oldCanvasW/H: canvas dimensions in pixels BEFORE the rotation (PDF pts × scale).
 * deltaRot: CW degrees being applied to the page (90, 180, or 270).
 */
export function transformOverlayForRotation(
  fabricJSON: string,
  oldCanvasW: number,
  oldCanvasH: number,
  deltaRot: 90 | 180 | 270
): string {
  if (!fabricJSON) return fabricJSON;
  let parsed: { objects?: Record<string, unknown>[]; [k: string]: unknown };
  try {
    parsed = JSON.parse(fabricJSON) as typeof parsed;
  } catch {
    return fabricJSON;
  }
  if (!parsed.objects?.length) return fabricJSON;

  parsed.objects = parsed.objects.map((obj) => {
    const left = (obj.left as number) ?? 0;
    const top = (obj.top as number) ?? 0;
    const objW = ((obj.width as number) ?? 0) * ((obj.scaleX as number) ?? 1);
    const objH = ((obj.height as number) ?? 0) * ((obj.scaleY as number) ?? 1);
    const angle = (obj.angle as number) ?? 0;

    // Bounding-box center in the old canvas space
    const cx = left + objW / 2;
    const cy = top + objH / 2;

    let newCx: number, newCy: number;
    if (deltaRot === 90) {
      // 90° CW: (x,y) → (H-y, x)
      newCx = oldCanvasH - cy;
      newCy = cx;
    } else if (deltaRot === 180) {
      newCx = oldCanvasW - cx;
      newCy = oldCanvasH - cy;
    } else {
      // 270° CW (= 90° CCW): (x,y) → (y, W-x)
      newCx = cy;
      newCy = oldCanvasW - cx;
    }

    return {
      ...obj,
      left: newCx - objW / 2,
      top: newCy - objH / 2,
      angle: (angle + deltaRot) % 360,
    };
  });

  return JSON.stringify(parsed);
}
