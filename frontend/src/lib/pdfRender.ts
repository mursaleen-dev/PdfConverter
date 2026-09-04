import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
// @ts-expect-error -- no type declarations for this subpath; we only need its side effect below
import * as pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs";

// Run PDF parsing on the main thread instead of spawning a real Web Worker.
// The dedicated Worker's handshake can hang indefinitely in some sandboxed
// browser environments with no fallback, so we skip it entirely.
if (typeof window !== "undefined") {
  (window as unknown as { pdfjsWorker: unknown }).pdfjsWorker = pdfjsWorker;
}

// Canvas render scale: 1 PDF point → PDF_RENDER_SCALE canvas pixels.
// Exported so callers can convert canvas-pixel font sizes back to PDF points
// before sending them to the backend (fontSizePt = fontSizePx / PDF_RENDER_SCALE).
export const PDF_RENDER_SCALE = 1.4;

/** Options that keep pdf.js from substituting OS fonts for embedded/Type3 faces. */
export const PDF_DOCUMENT_OPTIONS = {
  useSystemFonts: false,
} as const;

export function canvasOutputScale(): number {
  if (typeof window === "undefined") return 1;
  return Math.min(window.devicePixelRatio || 1, 3);
}

export function sizeCanvasForViewport(
  canvas: HTMLCanvasElement,
  cssWidth: number,
  cssHeight: number,
): number {
  const outputScale = canvasOutputScale();
  canvas.width = Math.max(1, Math.floor(cssWidth * outputScale));
  canvas.height = Math.max(1, Math.floor(cssHeight * outputScale));
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  return outputScale;
}

export interface RenderedPageSize {
  width: number;
  height: number;
}

export interface PageRenderHandle {
  promise: Promise<RenderedPageSize>;
  cancel: () => void;
}

export async function loadPdf(file: File): Promise<PDFDocumentProxy> {
  const buffer = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({ data: buffer, ...PDF_DOCUMENT_OPTIONS });
  return loadingTask.promise;
}

export function renderPageToCanvas(
  pdf: PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  scale = PDF_RENDER_SCALE
): PageRenderHandle {
  let cancelled = false;
  let renderTask: ReturnType<import("pdfjs-dist").PDFPageProxy["render"]> | null = null;

  const promise = (async () => {
    const page = await pdf.getPage(pageNumber);
    if (cancelled) throw new Error("cancelled");

    const viewport = page.getViewport({ scale });
    const outputScale = sizeCanvasForViewport(canvas, viewport.width, viewport.height);
    const renderViewport = outputScale === 1
      ? viewport
      : page.getViewport({ scale: scale * outputScale });
    canvas.width = renderViewport.width;
    canvas.height = renderViewport.height;

    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not get canvas 2D context");

    // intent: "print" disables pdf.js's requestAnimationFrame-driven render
    // scheduling (used for the default "display" intent), which never fires
    // in some sandboxed/background browser tabs and would hang forever.
    renderTask = page.render({ canvasContext: context, viewport: renderViewport, canvas, intent: "print" });
    await renderTask.promise;
    return { width: viewport.width, height: viewport.height };
  })();

  return {
    promise,
    cancel: () => {
      cancelled = true;
      renderTask?.cancel();
    },
  };
}
