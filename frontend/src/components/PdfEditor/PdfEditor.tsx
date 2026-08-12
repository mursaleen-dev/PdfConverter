"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ImagePlus,
  PenLine,
  Type,
  MousePointer2,
} from "lucide-react";
import FileDropzone from "@/components/FileDropzone";
import ProgressBar from "@/components/ProgressBar";
import ConversionResult from "@/components/ConversionResult";
import ElementBox from "./ElementBox";
import TextSpanOverlay from "./TextSpanOverlay";
import SignatureModal from "./SignatureModal";
import type { EditorElement, EditorMode, PageSize, PdfTextSpan } from "./types";
import { loadPdf, renderPageToCanvas, PDF_RENDER_SCALE } from "@/lib/pdfRender";
import { extractPageTextSpans } from "@/lib/pdfText";
import {
  editPdf,
  ConvertError,
  type EditElementPayload,
  type TextReplacementPayload,
} from "@/lib/api";
import { MAX_FILE_SIZE_MB, isAcceptedFile } from "@/lib/constants";
import type { PDFDocumentProxy } from "pdfjs-dist";

type Status = "idle" | "editing" | "saving" | "success" | "error";

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function getImageSize(dataUrl: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = reject;
    img.src = dataUrl;
  });
}

let elementIdCounter = 0;
function nextId() {
  elementIdCounter += 1;
  return `el-${elementIdCounter}`;
}

export default function PdfEditor() {
  const [status, setStatus] = useState<Status>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSizes, setPageSizes] = useState<Record<number, PageSize>>({});

  // ── Annotate mode state ────────────────────────────────────────────────────
  const [elements, setElements] = useState<EditorElement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // ── Edit Text mode state ───────────────────────────────────────────────────
  const [mode, setMode] = useState<EditorMode>("annotate");
  // textSpans for the current page (loaded on demand, cached by page number)
  const [textSpans, setTextSpans] = useState<PdfTextSpan[]>([]);
  const [spansLoading, setSpansLoading] = useState(false);
  // spanId → new text; only spans the user has actually changed are stored here
  const [textEdits, setTextEdits] = useState<Record<string, string>>({});
  // Cache extracted spans per page to avoid re-extracting on page navigation
  const textSpansCacheRef = useRef<Record<number, PdfTextSpan[]>>({});

  // ── Shared state ───────────────────────────────────────────────────────────
  const [signatureModalOpen, setSignatureModalOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<{ downloadUrl: string; filename: string } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stampInputRef = useRef<HTMLInputElement>(null);
  const objectUrlRef = useRef<string | null>(null);

  // Revoke object URL on unmount
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  // Re-render the canvas whenever the page or PDF changes
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    const handle = renderPageToCanvas(pdfDoc, currentPage, canvasRef.current);
    handle.promise
      .then((size) => {
        setPageSizes((prev) => ({ ...prev, [currentPage]: size }));
      })
      .catch(() => {
        // Cancelled renders from React Strict Mode or fast page navigation are expected.
      });
    return () => handle.cancel();
  }, [pdfDoc, currentPage]);

  // Load (or restore from cache) text spans when entering text-edit mode or
  // navigating to a new page while in that mode.
  useEffect(() => {
    if (mode !== "text-edit" || !pdfDoc) {
      setTextSpans([]);
      return;
    }

    const cached = textSpansCacheRef.current[currentPage];
    if (cached) {
      setTextSpans(cached);
      return;
    }

    let cancelled = false;
    setSpansLoading(true);

    pdfDoc
      .getPage(currentPage)
      .then((page) => extractPageTextSpans(page, currentPage))
      .then((spans) => {
        if (cancelled) return;
        textSpansCacheRef.current[currentPage] = spans;
        setTextSpans(spans);
      })
      .catch(() => {
        if (!cancelled) setTextSpans([]);
      })
      .finally(() => {
        if (!cancelled) setSpansLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mode, pdfDoc, currentPage]);

  const handleFileSelected = async (selected: File) => {
    if (!isAcceptedFile(selected, [".pdf"])) {
      setStatus("error");
      setErrorMessage("Unsupported file type. Please choose a PDF file.");
      return;
    }
    if (selected.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setStatus("error");
      setErrorMessage(`File exceeds the maximum allowed size of ${MAX_FILE_SIZE_MB} MB.`);
      return;
    }

    try {
      const doc = await loadPdf(selected);
      setFile(selected);
      setPdfDoc(doc);
      setNumPages(doc.numPages);
      setCurrentPage(1);
      setPageSizes({});
      setElements([]);
      setSelectedId(null);
      setMode("annotate");
      setTextEdits({});
      textSpansCacheRef.current = {};
      setStatus("editing");
    } catch {
      setStatus("error");
      setErrorMessage("This PDF could not be opened. It may be corrupted.");
    }
  };

  const currentPageSize = pageSizes[currentPage];

  // ── Annotate mode actions ──────────────────────────────────────────────────

  const addTextElement = () => {
    if (!currentPageSize) return;
    const width = 220;
    const height = 54;
    const id = nextId();
    setElements((prev) => [
      ...prev,
      {
        id,
        page: currentPage,
        type: "text",
        x: Math.max(0, currentPageSize.width / 2 - width / 2),
        y: Math.max(0, currentPageSize.height / 2 - height / 2),
        width,
        height,
        text: "Double-click to edit",
        // 16 canvas-px ÷ 1.4 render scale ≈ 11.4 PDF points (comfortable body size)
        fontSize: 16,
        fontFamily: "helvetica",
        bold: false,
        italic: false,
        underline: false,
        color: "#111111",
      },
    ]);
    setSelectedId(id);
  };

  const addImageElement = async (dataUrl: string) => {
    if (!currentPageSize) return;
    const natural = await getImageSize(dataUrl);
    const maxWidth = 200;
    const scale = Math.min(1, maxWidth / natural.width);
    const width = natural.width * scale;
    const height = natural.height * scale;
    const id = nextId();
    setElements((prev) => [
      ...prev,
      {
        id,
        page: currentPage,
        type: "image",
        x: Math.max(0, currentPageSize.width / 2 - width / 2),
        y: Math.max(0, currentPageSize.height / 2 - height / 2),
        width,
        height,
        imageDataUrl: dataUrl,
      },
    ]);
    setSelectedId(id);
  };

  const handleStampSelected = async (fileList: FileList | null) => {
    const stampFile = fileList?.[0];
    if (!stampFile) return;
    const dataUrl = await readFileAsDataUrl(stampFile);
    await addImageElement(dataUrl);
    if (stampInputRef.current) stampInputRef.current.value = "";
  };

  const updateElement = (id: string, patch: Partial<EditorElement>) => {
    setElements((prev) => prev.map((el) => (el.id === id ? { ...el, ...patch } : el)));
  };

  const deleteElement = (id: string) => {
    setElements((prev) => prev.filter((el) => el.id !== id));
    setSelectedId((cur) => (cur === id ? null : cur));
  };

  // ── Edit Text mode actions ─────────────────────────────────────────────────

  const handleSpanEdit = (spanId: string, newText: string) => {
    setTextEdits((prev) => ({ ...prev, [spanId]: newText }));
  };

  // ── Reset ──────────────────────────────────────────────────────────────────

  const reset = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setStatus("idle");
    setFile(null);
    setPdfDoc(null);
    setNumPages(0);
    setCurrentPage(1);
    setPageSizes({});
    setElements([]);
    setSelectedId(null);
    setMode("annotate");
    setTextSpans([]);
    setTextEdits({});
    textSpansCacheRef.current = {};
    setProgress(0);
    setErrorMessage("");
    setResult(null);
  };

  // ── Save ───────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!file) return;

    // Build overlay element payload (annotate mode additions)
    const overlayPayload: EditElementPayload[] = elements
      .filter((el) => pageSizes[el.page])
      .map((el) => {
        const size = pageSizes[el.page];
        return {
          page: el.page - 1,
          type: el.type,
          x: el.x / size.width,
          y: el.y / size.height,
          width: el.width / size.width,
          height: el.height / size.height,
          text: el.text,
          // Divide canvas pixels by render scale → PDF points
          fontSize: el.fontSize != null ? el.fontSize / PDF_RENDER_SCALE : undefined,
          fontFamily: el.fontFamily,
          bold: el.bold,
          italic: el.italic,
          underline: el.underline,
          color: el.color,
          image: el.imageDataUrl,
        };
      });

    // Build text-replacement payload (edit-text mode changes).
    // Only include spans whose text actually changed — no-op entries would
    // trigger a pointless redact+reinsert cycle on the backend.
    const allSpans = Object.values(textSpansCacheRef.current).flat();
    const textPayload: TextReplacementPayload[] = Object.entries(textEdits)
      .map(([spanId, newText]) => {
        const span = allSpans.find((s) => s.id === spanId);
        if (!span) return null;
        if (newText === span.text) return null;   // skip unchanged edits
        return {
          page:       span.page - 1,   // 0-indexed for backend
          x0:         span.pdfX0,
          y0:         span.pdfY0,
          x1:         span.pdfX1,
          y1:         span.pdfY1,
          new_text:   newText,
          baseline_y: span.pdfBaselineY,
        };
      })
      .filter((r): r is TextReplacementPayload => r !== null);

    setStatus("saving");
    setProgress(0);
    setErrorMessage("");

    try {
      const { blob, filename } = await editPdf(
        file,
        overlayPayload,
        setProgress,
        textPayload
      );
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setResult({ downloadUrl: url, filename });
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ConvertError ? err.message : "Something went wrong. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const pendingEdits = Object.keys(textEdits).length + elements.length;

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 px-4 py-8 font-sans dark:bg-black">
      <div className="flex w-full max-w-4xl flex-col gap-4">
        <Link
          href="/"
          className="inline-flex w-fit items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to tools
        </Link>

        {status === "idle" && (
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
            <div className="text-center">
              <h1 className="text-xl font-semibold">Edit PDF</h1>
              <p className="mt-1 text-sm text-neutral-500">
                Add text, stamps, and signatures — or edit existing text directly
              </p>
            </div>
            <FileDropzone onFileSelected={handleFileSelected} acceptedExtensions={[".pdf"]} />
          </div>
        )}

        {status === "error" && !file && (
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-3 rounded-2xl border border-neutral-200 bg-white p-8 text-center shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
            <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
            <button
              onClick={reset}
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
            >
              Try again
            </button>
          </div>
        )}

        {(status === "editing" || status === "saving" || (status === "error" && file)) && (
          <div className="flex flex-col gap-4">
            {/* ── Toolbar ── */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-neutral-200 bg-white px-4 py-3 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
              {/* Mode toggle */}
              <div className="flex items-center gap-1 rounded-lg border border-neutral-200 p-1 dark:border-neutral-800">
                <button
                  onClick={() => setMode("annotate")}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors ${
                    mode === "annotate"
                      ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
                      : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
                  }`}
                >
                  <Type className="h-3.5 w-3.5" />
                  Annotate
                </button>
                <button
                  onClick={() => setMode("text-edit")}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors ${
                    mode === "text-edit"
                      ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
                      : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
                  }`}
                >
                  <MousePointer2 className="h-3.5 w-3.5" />
                  Edit Text
                </button>
              </div>

              {/* Annotate mode tools */}
              {mode === "annotate" && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={addTextElement}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 px-3 py-1.5 text-sm font-medium hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
                  >
                    <Type className="h-4 w-4" />
                    Text
                  </button>
                  <button
                    onClick={() => stampInputRef.current?.click()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 px-3 py-1.5 text-sm font-medium hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
                  >
                    <ImagePlus className="h-4 w-4" />
                    Stamp
                  </button>
                  <input
                    ref={stampInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => handleStampSelected(e.target.files)}
                  />
                  <button
                    onClick={() => setSignatureModalOpen(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 px-3 py-1.5 text-sm font-medium hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
                  >
                    <PenLine className="h-4 w-4" />
                    Signature
                  </button>
                </div>
              )}

              {/* Edit Text mode hint */}
              {mode === "text-edit" && (
                <p className="text-xs text-neutral-500">
                  {spansLoading
                    ? "Detecting text…"
                    : textSpans.length === 0
                    ? "No editable text detected on this page"
                    : `${textSpans.filter((s) => !s.isRotated).length} editable text objects — hover to highlight, click to edit`}
                </p>
              )}

              {/* Page navigation */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  aria-label="Previous page"
                  className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-800"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-xs text-neutral-500">
                  Page {currentPage} / {numPages}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(numPages, p + 1))}
                  disabled={currentPage >= numPages}
                  aria-label="Next page"
                  className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-800"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>

              <button
                onClick={handleSave}
                disabled={status === "saving"}
                className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                {status === "saving"
                  ? "Saving…"
                  : pendingEdits > 0
                  ? `Save PDF (${pendingEdits} change${pendingEdits !== 1 ? "s" : ""})`
                  : "Save PDF"}
              </button>
            </div>

            {status === "saving" && (
              <div className="mx-auto w-full max-w-sm">
                <ProgressBar percent={progress} />
              </div>
            )}

            {status === "error" && (
              <p className="text-center text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
            )}

            {/* ── Canvas + overlays ── */}
            <div
              className="mx-auto overflow-auto rounded-xl border border-neutral-200 bg-neutral-100 p-4 dark:border-neutral-800 dark:bg-neutral-900"
              onMouseDown={(e) => {
                if (e.target === e.currentTarget) setSelectedId(null);
              }}
            >
              <div
                className="relative mx-auto bg-white shadow"
                style={{
                  width: currentPageSize?.width ?? 600,
                  height: currentPageSize?.height ?? 800,
                }}
                onMouseDown={(e) => {
                  if (e.target === e.currentTarget) setSelectedId(null);
                }}
              >
                {/* PDF rendered to canvas */}
                <canvas ref={canvasRef} className="absolute inset-0" />

                {/* Annotate mode: drag-and-drop overlay elements */}
                {mode === "annotate" &&
                  elements
                    .filter((el) => el.page === currentPage)
                    .map((el) => (
                      <ElementBox
                        key={el.id}
                        element={el}
                        selected={selectedId === el.id}
                        onSelect={() => setSelectedId(el.id)}
                        onChange={(patch) => updateElement(el.id, patch)}
                        onDelete={() => deleteElement(el.id)}
                      />
                    ))}

                {/* Edit Text mode: click-to-edit overlays over existing text */}
                {mode === "text-edit" &&
                  !spansLoading &&
                  textSpans
                    .filter((s) => s.page === currentPage)
                    .map((span) => (
                      <TextSpanOverlay
                        key={span.id}
                        span={span}
                        editedText={textEdits[span.id]}
                        onEdit={(newText) => handleSpanEdit(span.id, newText)}
                      />
                    ))}
              </div>
            </div>
          </div>
        )}

        {status === "success" && result && (
          <div className="mx-auto w-full max-w-md rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
            <ConversionResult
              downloadUrl={result.downloadUrl}
              filename={result.filename}
              onReset={reset}
            />
          </div>
        )}
      </div>

      {signatureModalOpen && (
        <SignatureModal
          onClose={() => setSignatureModalOpen(false)}
          onConfirm={(dataUrl) => {
            setSignatureModalOpen(false);
            addImageElement(dataUrl);
          }}
        />
      )}
    </div>
  );
}
