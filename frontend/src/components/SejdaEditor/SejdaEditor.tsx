"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  RotateCcw,
  Trash2,
  Copy,
  PlusSquare,
  LayoutGrid,
  Undo2,
  Redo2,
  Search,
} from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
// @ts-expect-error no type declarations for this subpath
import * as pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import FileDropzone from "@/components/FileDropzone";
import ProgressBar from "@/components/ProgressBar";
import ConversionResult from "@/components/ConversionResult";
import SignatureModal from "@/components/PdfEditor/SignatureModal";
import FabricPage, { FabricPageHandle, fabricJSONToManifest, type SelectionBounds } from "./FabricPage";
import Toolbar from "./Toolbar";
import PageSidebar from "./PageSidebar";
import OrganizeGrid from "./OrganizeGrid";
import TextHitLayer from "./TextHitLayer";
import InlineEditor from "./InlineEditor";
import TextEditPreviewLayer, { type TextEditPreview } from "./TextEditPreviewLayer";
import FindReplace from "./FindReplace";
import { SelectionToolbar, ContextMenu } from "./ObjectActionMenu";
import {
  DEFAULT_TOOL_SETTINGS,
  type ActiveTool,
  type EmbeddedFontFace,
  type ExtractedPage,
  type ExtractedParagraph,
  type ExtractedSpan,
  type ManifestObject,
  type TextEditEntry,
  type TextRun,
  type ToolSettings,
} from "./types";
import { useEditorState } from "./useEditorState";
import { useTextExtract } from "./useTextExtract";
import { applySejdaManifest, ConvertError } from "@/lib/api";
import { MAX_FILE_SIZE_MB, isAcceptedFile } from "@/lib/constants";
import { PDF_DOCUMENT_OPTIONS } from "@/lib/pdfRender";
import { PREVIEW_FONT_PREFIX } from "./previewFonts";

if (typeof window !== "undefined") {
  (window as unknown as { pdfjsWorker: unknown }).pdfjsWorker = pdfjsWorker;
}

type Status = "idle" | "editing" | "saving" | "success" | "error";

const MIN_SCALE = 0.5;
const MAX_SCALE = 3.0;
const SCALE_STEP = 0.25;
const loadedEmbeddedFonts = new Set<string>();
const loadingEmbeddedFonts = new Map<string, Promise<void>>();

function normalizeFontFaces(
  fonts?: Record<string, string> | EmbeddedFontFace[],
): EmbeddedFontFace[] {
  if (!fonts) return [];
  if (Array.isArray(fonts)) return fonts.filter((face) => face?.family && face?.src);
  return Object.entries(fonts).map(([rawFamily, src]) => {
    const family = rawFamily.replace(/[^A-Za-z0-9 _-]/g, "").trim();
    const lower = family.toLowerCase();
    return {
      family,
      src,
      weight: /bold|black|heavy|demi|semibold/.test(lower) ? "700" : "400",
      style: /italic|oblique|slanted/.test(lower) ? "italic" : "normal",
    };
  });
}

async function loadEmbeddedFonts(
  fonts?: Record<string, string> | EmbeddedFontFace[],
): Promise<void> {
  if (typeof FontFace === "undefined") return;
  await Promise.allSettled(normalizeFontFaces(fonts).map(async (face) => {
    const cleaned = face.family.replace(/[^A-Za-z0-9 _-]/g, "").trim();
    if (!cleaned) return;
    const family = `${PREVIEW_FONT_PREFIX}${cleaned}`;
    const weight = face.weight || "400";
    const style = face.style || "normal";
    const cacheKey = `${family}:${weight}:${style}:${face.src.length}:${face.src.slice(-24)}`;
    if (loadedEmbeddedFonts.has(cacheKey)) return;
    const existing = loadingEmbeddedFonts.get(cacheKey);
    if (existing) return existing;

    const pending = new FontFace(family, `url("${face.src}")`, {
      weight,
      style,
    }).load().then((loaded) => {
      document.fonts.add(loaded);
      loadedEmbeddedFonts.add(cacheKey);
    }).finally(() => {
      loadingEmbeddedFonts.delete(cacheKey);
    });
    loadingEmbeddedFonts.set(cacheKey, pending);
    return pending;
  }));
}

function bboxToRect(
  bbox: [number, number, number, number],
  pageW: number,
  pageH: number,
  rotation: number,
  scale: number
): { left: number; top: number; width: number; height: number } {
  const [x0, y0, x1, y1] = bbox;
  const t = (px: number, py: number) => {
    switch (rotation) {
      case 90:  return { x: (pageH - py) * scale, y: px * scale };
      case 180: return { x: (pageW - px) * scale, y: (pageH - py) * scale };
      case 270: return { x: py * scale, y: (pageW - px) * scale };
      default:  return { x: px * scale, y: py * scale };
    }
  };
  const corners = [t(x0, y0), t(x1, y0), t(x0, y1), t(x1, y1)];
  const xs = corners.map((c) => c.x);
  const ys = corners.map((c) => c.y);
  const left = Math.min(...xs);
  const top  = Math.min(...ys);
  return { left, top, width: Math.max(...xs) - left, height: Math.max(...ys) - top };
}

function findExistingTextEdit(
  edits: readonly TextEditEntry[],
  spanIds: string[],
): TextEditEntry | undefined {
  if (spanIds.length === 0) return undefined;
  const key = spanIds.join(",");
  for (let i = edits.length - 1; i >= 0; i--) {
    if (edits[i].spanIds.join(",") === key) return edits[i];
  }
  const wanted = new Set(spanIds);
  for (let i = edits.length - 1; i >= 0; i--) {
    if (edits[i].spanIds.some((id) => wanted.has(id))) return edits[i];
  }
  return undefined;
}

export default function SejdaEditor() {
  const [status, setStatus] = useState<Status>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfPage, setPdfPage] = useState<PDFPageProxy | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageLoadError, setPageLoadError] = useState("");
  const [pageLoadAttempt, setPageLoadAttempt] = useState(0);
  const [scale, setScale] = useState(1.4);
  const [activeTool, setActiveTool] = useState<ActiveTool>("select");
  const [toolSettings, setToolSettings] = useState<ToolSettings>(DEFAULT_TOOL_SETTINGS);
  const [sigModalOpen, setSigModalOpen] = useState(false);
  const [pendingImageTool, setPendingImageTool] = useState<"image" | "signature">("image");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<{ downloadUrl: string; filename: string; warnings?: string[] } | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [organizeMode, setOrganizeMode] = useState(false);
  const [findReplaceOpen, setFindReplaceOpen] = useState(false);

  // Fabric selection / context menu
  const [selectionBounds, setSelectionBounds] = useState<SelectionBounds | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);

  // Phase 3: text edit state
  const [activeParaForEdit, setActiveParaForEdit] = useState<ExtractedParagraph | null>(null);
  const [activeSingleSpan, setActiveSingleSpan] = useState<ExtractedSpan | null>(null);
  const [currentPageExtracted, setCurrentPageExtracted] = useState<ExtractedPage | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState("");
  const [extractAttempt, setExtractAttempt] = useState(0);
  const [textEditPreviews, setTextEditPreviews] = useState<Map<string, TextEditPreview>>(new Map());

  // Shared thumbnail cache: key → data URL
  const thumbCache = useRef<Map<string, string>>(new Map());

  const editorState = useEditorState();
  const textExtract = useTextExtract();

  const fabricPageRef = useRef<FabricPageHandle | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  // Load the PDF page for the current editing page
  useEffect(() => {
    if (!pdfDoc || !editorState.currentEditingPageId) return;
    const desc = editorState.pages.find((p) => p.pageId === editorState.currentEditingPageId);
    if (!desc || desc.isBlank) { setPdfPage(null); setPageLoading(false); return; }
    let cancelled = false;
    setPdfPage(null);
    setPageLoadError("");
    setPageLoading(true);
    pdfDoc.getPage(desc.sourceIndex + 1)
      .then((page) => {
        if (!cancelled) setPdfPage(page);
      })
      .catch(() => {
        if (!cancelled) setPageLoadError(`Page ${desc.sourceIndex + 1} could not be loaded.`);
      })
      .finally(() => {
        if (!cancelled) setPageLoading(false);
      });
    return () => { cancelled = true; };
  }, [pdfDoc, editorState.currentEditingPageId, editorState.pages, pageLoadAttempt]);

  // Live overlay sync (no undo entry — just keeps React state fresh).
  const handleStateChange = useCallback(
    (json: string) => {
      editorState.setOverlay(editorState.currentEditingPageId, json);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editorState.currentEditingPageId, editorState.setOverlay]
  );

  // Committed mutation → push onto command stack.
  const handleUndoableChange = useCallback(
    (before: string, after: string, label: string) => {
      editorState.overlayChangeCmd(editorState.currentEditingPageId, before, after, label);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editorState.currentEditingPageId, editorState.overlayChangeCmd]
  );

  const handleSelectionChange = useCallback((bounds: SelectionBounds | null) => {
    setSelectionBounds(bounds);
  }, []);

  const handleContextMenu = useCallback((screenX: number, screenY: number) => {
    setContextMenu({ x: screenX, y: screenY });
  }, []);

  const flushCurrentPage = useCallback(() => {
    if (fabricPageRef.current && editorState.currentEditingPageId) {
      editorState.setOverlay(editorState.currentEditingPageId, fabricPageRef.current.getJSON());
    }
  }, [editorState]);

  // Undo/redo with canvas reload for the current page.
  const handleUndo = useCallback(() => {
    flushCurrentPage();
    editorState.undo((overlays) => {
      const json = overlays[editorState.currentEditingPageId];
      if (json !== undefined && fabricPageRef.current) {
        fabricPageRef.current.loadJSON(json);
      }
    });
    setSelectionBounds(null);
    setContextMenu(null);
  }, [editorState, flushCurrentPage]);

  const handleRedo = useCallback(() => {
    editorState.redo((overlays) => {
      const json = overlays[editorState.currentEditingPageId];
      if (json !== undefined && fabricPageRef.current) {
        fabricPageRef.current.loadJSON(json);
      }
    });
    setSelectionBounds(null);
    setContextMenu(null);
  }, [editorState]);

  // Sync preview map with undo/redo: remove previews for edits that are no longer in textEdits.
  useEffect(() => {
    setTextEditPreviews((m) => {
      if (m.size === 0) return m;
      const currentKeys = new Set(editorState.textEdits.map((e) => e.spanIds.join(",")));
      const next = new Map<string, TextEditPreview>();
      for (const [k, v] of m) {
        if (currentKeys.has(k)) next.set(k, v);
      }
      return next.size === m.size ? m : next;
    });
  }, [editorState.textEdits]);

  // Global Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y keyboard shortcuts.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const meta = e.ctrlKey || e.metaKey;
      if (!meta) return;
      const target = e.target as HTMLElement;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target.isContentEditable ||
        fabricPageRef.current?.isTextEditing()
      ) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((e.key === "z" && e.shiftKey) || e.key === "y") {
        e.preventDefault();
        handleRedo();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [handleUndo, handleRedo]);

  const handleFileSelected = async (selected: File) => {
    if (!isAcceptedFile(selected, [".pdf"])) {
      setStatus("error");
      setErrorMessage("Please choose a PDF file.");
      return;
    }
    if (selected.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setStatus("error");
      setErrorMessage(`File exceeds the ${MAX_FILE_SIZE_MB} MB limit.`);
      return;
    }
    try {
      const buf = await selected.arrayBuffer();
      const doc = await pdfjsLib.getDocument({ data: buf, ...PDF_DOCUMENT_OPTIONS }).promise;
      setFile(selected);
      setPdfDoc(doc);
      thumbCache.current.clear();
      setActiveTool("select");
      setResult(null);
      setOrganizeMode(false);
      setSidebarCollapsed(false);
      await editorState.initFromDoc(doc);
      setStatus("editing");
    } catch {
      setStatus("error");
      setErrorMessage("This PDF could not be opened. It may be corrupted.");
    }
  };

  const goToPage = useCallback(
    (pageId: string) => {
      flushCurrentPage();
      editorState.navigateTo(pageId);
    },
    [flushCurrentPage, editorState]
  );

  const goToIndex = (delta: number) => {
    const current = editorState.pages;
    const idx = current.findIndex((p) => p.pageId === editorState.currentEditingPageId);
    const next = current[idx + delta];
    if (next) goToPage(next.pageId);
  };

  const handleSave = async () => {
    if (!file) return;
    flushCurrentPage();

    const manifest: ManifestObject[] = [];
    for (const [pageId, json] of Object.entries(editorState.overlays)) {
      try {
        const parsed = JSON.parse(json) as { objects?: unknown[] };
        const objects = fabricJSONToManifest(parsed, pageId, scale);
        manifest.push(...objects);
      } catch {/* skip corrupt page */}
    }

    setStatus("saving");
    setProgress(0);
    setErrorMessage("");

    try {
      const { blob, filename, warnings } = await applySejdaManifest(
        file,
        manifest,
        editorState.pages,
        editorState.textEdits.length > 0 ? editorState.textEdits : undefined,
        setProgress
      );
      const url = URL.createObjectURL(blob);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = url;
      setResult({ downloadUrl: url, filename, warnings });
      setStatus("success");
      setTextEditPreviews(new Map());
    } catch (err) {
      const msg = err instanceof ConvertError ? err.message : "Something went wrong. Please try again.";
      setErrorMessage(msg);
      setStatus("error");
    }
  };

  const reset = () => {
    setStatus("idle");
    setFile(null);
    setPdfDoc(null);
    setPdfPage(null);
    setResult(null);
    setErrorMessage("");
    setOrganizeMode(false);
    setFindReplaceOpen(false);
    setSelectionBounds(null);
    setContextMenu(null);
    setExtracting(false);
    setCurrentPageExtracted(null);
    setActiveParaForEdit(null);
    setActiveSingleSpan(null);
    setTextEditPreviews(new Map());
    thumbCache.current.clear();
    textExtract.clear();
    editorState.reset();
  };

  const handleSettingsChange = useCallback((patch: Partial<ToolSettings>) => {
    setToolSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  const handleAddImage = () => {
    setPendingImageTool("image");
    imageInputRef.current?.click();
  };

  const handleAddSignature = () => {
    setPendingImageTool("signature");
    setSigModalOpen(true);
  };

  const handleImageFileSelected = (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      fabricPageRef.current?.addImageFromDataUrl(reader.result as string, "image");
      setActiveTool("select");
    };
    reader.readAsDataURL(f);
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const handleSignatureConfirmed = (dataUrl: string) => {
    setSigModalOpen(false);
    fabricPageRef.current?.addImageFromDataUrl(dataUrl, "signature");
    setActiveTool("select");
  };

  // ── Phase 3: text edit ────────────────────────────────────────────────────

  // Trigger extraction when entering edit-text mode on the current page.
  useEffect(() => {
    if (activeTool !== "edit-text" || !file || !currentDesc || currentDesc.isBlank) {
      setCurrentPageExtracted(null);
      setExtracting(false);
      return;
    }
    let cancelled = false;
    setCurrentPageExtracted(null);
    setExtractError("");
    setExtracting(true);
    textExtract
      .getPage(file, currentDesc.pageId, currentDesc.sourceIndex)
      .then(async (page) => {
        if (page) await loadEmbeddedFonts(page.fonts);
        if (!cancelled) {
          setCurrentPageExtracted(page);
          if (!page) setExtractError("Text could not be loaded for this page.");
          setExtracting(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setExtractError("Text could not be loaded for this page.");
          setExtracting(false);
        }
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool, file, editorState.currentEditingPageId, extractAttempt]);

  const handleParaClick = (para: ExtractedParagraph) => {
    if (!file || !currentDesc) return;
    setActiveParaForEdit(para);
    setActiveSingleSpan(null);
  };

  const handleSpanClick = (para: ExtractedParagraph, span: ExtractedSpan) => {
    setActiveParaForEdit(para);
    setActiveSingleSpan(span);
  };

  const handleInlineCommit = (runs: TextRun[]) => {
    if (!activeParaForEdit || !currentDesc) return;
    const entry: TextEditEntry = {
      type: "textEdit",
      pageId: currentDesc.pageId,
      spanIds: activeSingleSpan
        ? (activeSingleSpan.memberSpanIds ?? [activeSingleSpan.spanId])
        : activeParaForEdit.spanIds,
      newText: runs,
      overflowPolicy: "shrink",
    };

    // Build optimistic preview before committing
    const targetSpans = activeSingleSpan
      ? [activeSingleSpan]
      : activeParaForEdit.lines.flatMap((l) => l.spans);
    if (targetSpans.length > 0) {
      const x0 = Math.min(...targetSpans.map((s) => s.bbox[0]));
      const x1 = Math.max(...targetSpans.map((s) => s.bbox[2]));
      // Stay inside the glyph box so the cover cannot white-out a table rule
      // that sits immediately under the cell value.
      const rawY0 = Math.min(...targetSpans.map((s) => s.bbox[1]));
      const rawY1 = Math.max(...targetSpans.map((s) => s.bbox[3]));
      const y0 = rawY0 + 0.4;
      const y1 = Math.max(y0 + 0.5, rawY1 - 0.7);
      const key = (activeSingleSpan
        ? (activeSingleSpan.memberSpanIds ?? [activeSingleSpan.spanId])
        : activeParaForEdit.spanIds
      ).join(",");
      setTextEditPreviews((m) =>
        new Map([...m, [key, {
          key,
          pageId: currentDesc.pageId,
          coverRect: [x0, y0, x1, y1],
          insertX: targetSpans[0]?.isLtr === false ? x1 : x0,
          insertY: targetSpans[0]?.baselineY ?? y1,
          runs,
          fontSize: targetSpans[0]?.size ?? 12,
          fontName: targetSpans[0]?.fontName ?? "",
          bold: targetSpans[0]?.bold ?? false,
          italic: targetSpans[0]?.italic ?? false,
          fontWeight: targetSpans[0]?.fontWeight,
          isLtr: targetSpans[0]?.isLtr ?? true,
          backgroundColor: targetSpans[0]?.backgroundColor ?? "#ffffff",
        }]])
      );
    }

    editorState.textEditCmd(entry);
    setActiveParaForEdit(null);
    setActiveSingleSpan(null);
  };

  const handleInlineCancel = () => {
    setActiveParaForEdit(null);
    setActiveSingleSpan(null);
  };

  // Current page descriptor
  const currentDesc = editorState.pages.find(
    (p) => p.pageId === editorState.currentEditingPageId
  );
  const currentIdx = editorState.pages.findIndex(
    (p) => p.pageId === editorState.currentEditingPageId
  );
  const selectedIds = [...editorState.selectedPageIds];
  const hasSelection = selectedIds.length > 0;

  const rotateSelected = (dir: "cw" | "ccw") => {
    flushCurrentPage();
    const ids = hasSelection ? selectedIds : editorState.currentEditingPageId ? [editorState.currentEditingPageId] : [];
    if (ids.length) editorState.rotatePagesCmd(ids, dir, scale);
  };

  return (
    <div className="flex flex-1 flex-col bg-zinc-50 px-4 py-8 font-sans dark:bg-black">
      <div className="flex w-full max-w-7xl mx-auto flex-col gap-4">
        <Link
          href="/"
          className="inline-flex w-fit items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to tools
        </Link>

        {/* ── Idle: upload ── */}
        {status === "idle" && (
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
            <div className="text-center">
              <h1 className="text-xl font-semibold">Edit PDF</h1>
              <p className="mt-1 text-sm text-neutral-500">
                Add text, shapes, images, signatures, and drawings. Reorder, rotate, or delete pages.
              </p>
            </div>
            <FileDropzone onFileSelected={handleFileSelected} acceptedExtensions={[".pdf"]} />
          </div>
        )}

        {/* ── Pre-file error ── */}
        {status === "error" && !file && (
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-3 rounded-2xl border border-neutral-200 bg-white p-8 text-center shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
            <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
            <button
              onClick={reset}
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-black"
            >
              Try again
            </button>
          </div>
        )}

        {/* ── Success ── */}
        {status === "success" && result && (
          <div className="flex flex-col items-center gap-3">
            <ConversionResult
              downloadUrl={result.downloadUrl}
              filename={result.filename}
              onReset={reset}
            />
            {result.warnings && result.warnings.length > 0 && (
              <div className="w-full max-w-md rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
                <p className="flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-4 w-4" />
                  Export completed with {result.warnings.length} warning{result.warnings.length !== 1 ? "s" : ""}
                </p>
                <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-xs text-amber-600 dark:text-amber-400">
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* ── Editor ── */}
        {(status === "editing" || status === "saving" || (status === "error" && file)) && (
          <div className="flex flex-col gap-3">
            {/* Toolbar */}
            <Toolbar
              activeTool={activeTool}
              onToolChange={setActiveTool}
              toolSettings={toolSettings}
              onSettingsChange={handleSettingsChange}
              onAddImage={handleAddImage}
              onAddSignature={handleAddSignature}
            />

            {status === "saving" && (
              <div className="mx-auto w-full max-w-sm">
                <ProgressBar percent={progress} />
              </div>
            )}

            {status === "error" && file && (
              <p className="text-center text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
            )}

            {/* Secondary bar: page ops + undo + nav + zoom + save */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-neutral-200 bg-white px-4 py-2 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
              {/* Organize */}
              <button
                onClick={() => setOrganizeMode((v) => !v)}
                className={[
                  "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                  organizeMode
                    ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-600 dark:bg-blue-900/30 dark:text-blue-300"
                    : "border-neutral-200 text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800",
                ].join(" ")}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                Organize
              </button>

              {/* Find & Replace */}
              <button
                onClick={() => setFindReplaceOpen((v) => !v)}
                className={[
                  "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                  findReplaceOpen
                    ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-600 dark:bg-blue-900/30 dark:text-blue-300"
                    : "border-neutral-200 text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800",
                ].join(" ")}
              >
                <Search className="h-3.5 w-3.5" />
                Find &amp; Replace
              </button>

              <div className="h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

              {/* Undo / Redo */}
              <button
                onClick={handleUndo}
                disabled={!editorState.canUndo}
                aria-label="Undo"
                className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-700"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                onClick={handleRedo}
                disabled={!editorState.canRedo}
                aria-label="Redo"
                className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-700"
              >
                <Redo2 className="h-4 w-4" />
              </button>

              <div className="h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

              {/* Page rotation/delete on current page (or selection) */}
              <button onClick={() => rotateSelected("ccw")} aria-label="Rotate CCW"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700">
                <RotateCcw className="h-4 w-4" />
              </button>
              <button onClick={() => rotateSelected("cw")} aria-label="Rotate CW"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700">
                <RotateCw className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  flushCurrentPage();
                  const ids = hasSelection ? selectedIds : editorState.currentEditingPageId ? [editorState.currentEditingPageId] : [];
                  if (ids.length && editorState.pages.length - ids.length >= 1) {
                    editorState.duplicatePagesCmd(ids);
                  }
                }}
                aria-label="Duplicate page"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700"
              >
                <Copy className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  flushCurrentPage();
                  const lastId = hasSelection
                    ? selectedIds[selectedIds.length - 1]
                    : editorState.currentEditingPageId;
                  if (lastId) editorState.insertBlankCmd(lastId);
                }}
                aria-label="Insert blank page"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700"
              >
                <PlusSquare className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  flushCurrentPage();
                  const ids = hasSelection ? selectedIds : editorState.currentEditingPageId ? [editorState.currentEditingPageId] : [];
                  if (ids.length && editorState.pages.length - ids.length >= 1) {
                    editorState.deletePagesCmd(ids);
                  }
                }}
                aria-label="Delete page"
                title="Delete page"
                className="flex items-center gap-1 rounded-lg border border-red-200 px-2 py-1.5 text-xs text-red-500 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/20"
              >
                <Trash2 className="h-4 w-4" />
                <span>Page</span>
              </button>

              <div className="h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

              {/* Page navigation */}
              <button
                onClick={() => goToIndex(-1)}
                disabled={currentIdx <= 0}
                aria-label="Previous page"
                className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-700"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-xs text-neutral-500 min-w-[5rem] text-center">
                {editorState.pages.length > 0
                  ? `Page ${currentIdx + 1} / ${editorState.pages.length}`
                  : "—"}
              </span>
              <button
                onClick={() => goToIndex(1)}
                disabled={currentIdx >= editorState.pages.length - 1}
                aria-label="Next page"
                className="rounded-lg border border-neutral-200 p-1.5 disabled:opacity-30 dark:border-neutral-700"
              >
                <ChevronRight className="h-4 w-4" />
              </button>

              <div className="h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

              {/* Zoom */}
              <button
                onClick={() => setScale((s) => Math.max(MIN_SCALE, parseFloat((s - SCALE_STEP).toFixed(2))))}
                aria-label="Zoom out"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <span className="w-12 text-center text-xs text-neutral-500">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(MAX_SCALE, parseFloat((s + SCALE_STEP).toFixed(2))))}
                aria-label="Zoom in"
                className="rounded-lg border border-neutral-200 p-1.5 dark:border-neutral-700"
              >
                <ZoomIn className="h-4 w-4" />
              </button>

              <div className="relative ml-auto">
                <button
                  onClick={handleSave}
                  disabled={status === "saving"}
                  className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
                >
                  {status === "saving" ? "Saving…" : "Save PDF"}
                </button>
                {textEditPreviews.size > 0 && (
                  <span className="pointer-events-none absolute -right-1 -top-1 flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
                  </span>
                )}
              </div>
            </div>

            {/* Main content: sidebar + canvas (or organize grid) */}
            <div
              className="relative flex overflow-hidden rounded-xl border border-neutral-200 bg-neutral-100 dark:border-neutral-800 dark:bg-neutral-900"
              style={{ minHeight: 520 }}
            >
              {!organizeMode && (
                <PageSidebar
                  pages={editorState.pages}
                  pdfDoc={pdfDoc}
                  thumbCache={thumbCache}
                  editorState={editorState}
                  collapsed={sidebarCollapsed}
                  onCollapsedChange={setSidebarCollapsed}
                />
              )}

              {organizeMode ? (
                <div className="flex-1 min-h-0">
                  <OrganizeGrid
                    pages={editorState.pages}
                    pdfDoc={pdfDoc}
                    thumbCache={thumbCache}
                    editorState={editorState}
                    scale={scale}
                    onClose={() => setOrganizeMode(false)}
                  />
                </div>
              ) : (
                <div className="flex-1 overflow-auto p-4">
                  {currentDesc?.isBlank ? (
                    // Blank page placeholder
                    <div
                      className="mx-auto bg-white shadow-lg flex items-center justify-center text-neutral-300 dark:text-neutral-600"
                      style={{
                        width: currentDesc.width * scale,
                        height: currentDesc.height * scale,
                      }}
                    >
                      <span className="text-sm">Blank page</span>
                    </div>
                  ) : pdfPage && currentDesc ? (
                    <div className="relative mx-auto w-fit">
                      <FabricPage
                        key={`page-${editorState.currentEditingPageId}-${currentDesc.rotation}-${scale}`}
                        ref={fabricPageRef}
                        pdfPage={pdfPage}
                        scale={scale}
                        userRotation={currentDesc.rotation}
                        activeTool={activeTool}
                        toolSettings={toolSettings}
                        initialJSON={editorState.overlays[editorState.currentEditingPageId]}
                        onStateChange={handleStateChange}
                        onUndoableChange={handleUndoableChange}
                        onSelectionChange={handleSelectionChange}
                        onContextMenu={handleContextMenu}
                      />
                      {/* Optimistic preview layer: shows committed-but-unsaved text edits */}
                      <TextEditPreviewLayer
                        previews={[...textEditPreviews.values()].filter(
                          (p) => p.pageId === editorState.currentEditingPageId
                        )}
                        scale={scale}
                        pageWidth={currentDesc.width}
                        pageHeight={currentDesc.height}
                        userRotation={currentDesc.rotation}
                      />
                      {/* Loading spinner while extracting text */}
                      {activeTool === "edit-text" && extracting && (
                        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                          <div className="rounded-lg bg-neutral-900/60 px-4 py-2 text-sm text-white backdrop-blur-sm">
                            Extracting text…
                          </div>
                        </div>
                      )}
                      {activeTool === "edit-text" && extractError && !extracting && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="rounded-lg bg-white/95 p-3 text-center shadow">
                            <p className="text-sm text-red-600">{extractError}</p>
                            <button
                              onClick={() => {
                                if (currentDesc) textExtract.invalidate(currentDesc.pageId);
                                setExtractAttempt((attempt) => attempt + 1);
                              }}
                              className="mt-2 rounded bg-neutral-900 px-3 py-1 text-xs text-white"
                            >
                              Retry text loading
                            </button>
                          </div>
                        </div>
                      )}
                      {/* Floating toolbar above selected Fabric objects */}
                      {activeTool !== "edit-text" && selectionBounds !== null && currentDesc && (
                        <SelectionToolbar
                          bounds={selectionBounds}
                          canvasWidth={
                            (currentDesc.rotation === 90 || currentDesc.rotation === 270
                              ? currentDesc.height
                              : currentDesc.width) * scale
                          }
                          onDelete={() => { fabricPageRef.current?.deleteSelected(); }}
                          onDuplicate={() => { fabricPageRef.current?.duplicateSelected(); }}
                          onBringForward={() => { fabricPageRef.current?.bringForward(); }}
                          onSendBackward={() => { fabricPageRef.current?.sendBackward(); }}
                        />
                      )}
                      {activeTool === "edit-text" && currentPageExtracted && !currentPageExtracted.scanned && (
                        <TextHitLayer
                          paragraphs={currentPageExtracted.paragraphs}
                          pageWidth={currentDesc.width}
                          pageHeight={currentDesc.height}
                          scale={scale}
                          userRotation={currentDesc.rotation}
                          onParaClick={handleParaClick}
                          onSpanClick={handleSpanClick}
                          activeParagraphId={activeParaForEdit?.paraId}
                        />
                      )}
                      {activeTool === "edit-text" && currentPageExtracted?.scanned && (
                        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                          <div className="rounded-lg bg-neutral-900/60 px-4 py-2 text-sm text-white backdrop-blur-sm">
                            Scanned page — text editing not available. Use the Text tool to add an overlay instead.
                          </div>
                        </div>
                      )}
                      {activeParaForEdit && (
                        <InlineEditor
                          para={activeParaForEdit}
                          singleSpan={activeSingleSpan}
                          rect={bboxToRect(
                            activeSingleSpan ? activeSingleSpan.bbox : activeParaForEdit.bbox,
                            currentDesc.width,
                            currentDesc.height,
                            currentDesc.rotation,
                            scale
                          )}
                          domSize={
                            (activeSingleSpan ?? activeParaForEdit.lines[0]?.spans[0])?.size ?? 12
                          }
                          scale={scale}
                          initialRuns={findExistingTextEdit(
                            editorState.textEdits,
                            activeSingleSpan
                              ? (activeSingleSpan.memberSpanIds ?? [activeSingleSpan.spanId])
                              : activeParaForEdit.spanIds,
                          )?.newText}
                          onCommit={handleInlineCommit}
                          onDelete={() => handleInlineCommit([])}
                          onCancel={handleInlineCancel}
                        />
                      )}
                    </div>
                  ) : (
                    <div className="flex min-h-[480px] flex-1 items-center justify-center">
                      {pageLoading ? (
                        <span className="text-sm text-neutral-500">Loading page…</span>
                      ) : pageLoadError ? (
                        <div className="text-center">
                          <p className="text-sm text-red-600">{pageLoadError}</p>
                          <button
                            onClick={() => setPageLoadAttempt((attempt) => attempt + 1)}
                            className="mt-2 rounded-lg bg-neutral-900 px-3 py-1.5 text-sm text-white"
                          >
                            Retry
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}

              {/* Floating Find & Replace panel */}
              {findReplaceOpen && file && (
                <div className="absolute right-4 top-4 z-20">
                  <FindReplace
                    file={file}
                    pages={editorState.pages}
                    extractAll={(pgs) => textExtract.extractAll(file, pgs)}
                    onApplyReplacements={(entries) => editorState.bulkTextEditCmd(entries)}
                    onClose={() => setFindReplaceOpen(false)}
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Hidden image input */}
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => handleImageFileSelected(e.target.files)}
      />

      {/* Right-click context menu for Fabric objects */}
      {contextMenu !== null && (
        <ContextMenu
          screenX={contextMenu.x}
          screenY={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onDelete={() => { fabricPageRef.current?.deleteSelected(); setContextMenu(null); }}
          onDuplicate={() => { fabricPageRef.current?.duplicateSelected(); setContextMenu(null); }}
          onBringForward={() => { fabricPageRef.current?.bringForward(); setContextMenu(null); }}
          onSendBackward={() => { fabricPageRef.current?.sendBackward(); setContextMenu(null); }}
        />
      )}

      {sigModalOpen && (
        <SignatureModal
          onConfirm={handleSignatureConfirmed}
          onClose={() => setSigModalOpen(false)}
        />
      )}
    </div>
  );
}
