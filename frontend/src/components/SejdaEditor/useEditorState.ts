import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageDescriptor, PageRotation, TextEditEntry } from "./types";
import {
  buildPageDescriptors,
  blankPageDims,
  makePageId,
  normalizeRotation,
  transformOverlayForRotation,
} from "./pageOps";

interface Snapshot {
  readonly pages: readonly PageDescriptor[];
  readonly overlays: Readonly<Record<string, string>>;
  readonly textEdits: readonly TextEditEntry[];
}

interface UndoEntry {
  before: Snapshot;
  after: Snapshot;
  label: string;
}

const MAX_UNDO = 100;

export interface EditorState {
  pages: PageDescriptor[];
  overlays: Record<string, string>;
  textEdits: TextEditEntry[];
  currentEditingPageId: string;
  selectedPageIds: ReadonlySet<string>;
  canUndo: boolean;
  canRedo: boolean;

  initFromDoc: (doc: PDFDocumentProxy) => Promise<void>;
  setOverlay: (pageId: string, json: string) => void;

  navigateTo: (pageId: string) => void;
  selectOnly: (pageId: string) => void;
  toggleSelect: (pageId: string) => void;
  rangeSelect: (pageId: string) => void;
  selectAll: () => void;
  clearSelection: () => void;

  rotatePagesCmd: (pageIds: string[], direction: "cw" | "ccw", scale: number) => void;
  deletePagesCmd: (pageIds: string[]) => void;
  reorderPagesCmd: (activeId: string, overId: string) => void;
  duplicatePagesCmd: (pageIds: string[]) => void;
  insertBlankCmd: (afterPageId: string) => void;
  textEditCmd: (entry: TextEditEntry) => void;
  bulkTextEditCmd: (entries: TextEditEntry[], label?: string) => void;
  clearTextEdits: () => void;
  overlayChangeCmd: (pageId: string, beforeJSON: string, afterJSON: string, label: string) => void;

  undo: (onRestored?: (overlays: Record<string, string>) => void) => void;
  redo: (onRestored?: (overlays: Record<string, string>) => void) => void;
  reset: () => void;
}

export function useEditorState(): EditorState {
  const [pages, setPages] = useState<PageDescriptor[]>([]);
  const [overlays, setOverlays] = useState<Record<string, string>>({});
  const [textEdits, setTextEdits] = useState<TextEditEntry[]>([]);
  const [currentEditingPageId, setCurrentEditingPageId] = useState("");
  const [selectedPageIds, setSelectedPageIds] = useState<ReadonlySet<string>>(new Set());
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // Keep current mutable state accessible in callbacks without stale closures
  const pagesRef = useRef<PageDescriptor[]>([]);
  const overlaysRef = useRef<Record<string, string>>({});
  const textEditsRef = useRef<TextEditEntry[]>([]);
  useEffect(() => { pagesRef.current = pages; }, [pages]);
  useEffect(() => { overlaysRef.current = overlays; }, [overlays]);
  useEffect(() => { textEditsRef.current = textEdits; }, [textEdits]);

  const undoStack = useRef<UndoEntry[]>([]);
  const undoPointer = useRef(-1);
  const lastClickedRef = useRef("");

  const applySnapshot = useCallback((snap: Snapshot) => {
    setPages([...snap.pages]);
    setOverlays({ ...snap.overlays });
    setTextEdits([...snap.textEdits]);
  }, []);

  const pushCommand = useCallback((before: Snapshot, after: Snapshot, label: string) => {
    // Trim any redo tail
    undoStack.current.length = undoPointer.current + 1;
    undoStack.current.push({ before, after, label });
    if (undoStack.current.length > MAX_UNDO) {
      undoStack.current.shift();
    } else {
      undoPointer.current++;
    }
    setCanUndo(undoPointer.current >= 0);
    setCanRedo(false);
    applySnapshot(after);
  }, [applySnapshot]);

  const undo = useCallback((onRestored?: (overlays: Record<string, string>) => void) => {
    if (undoPointer.current < 0) return;
    const entry = undoStack.current[undoPointer.current];
    undoPointer.current--;
    applySnapshot(entry.before);
    setCanUndo(undoPointer.current >= 0);
    setCanRedo(true);
    onRestored?.(entry.before.overlays as Record<string, string>);
  }, [applySnapshot]);

  const redo = useCallback((onRestored?: (overlays: Record<string, string>) => void) => {
    if (undoPointer.current >= undoStack.current.length - 1) return;
    undoPointer.current++;
    const entry = undoStack.current[undoPointer.current];
    applySnapshot(entry.after);
    setCanUndo(true);
    setCanRedo(undoPointer.current < undoStack.current.length - 1);
    onRestored?.(entry.after.overlays as Record<string, string>);
  }, [applySnapshot]);

  const initFromDoc = useCallback(async (doc: PDFDocumentProxy) => {
    const descs = await buildPageDescriptors(doc);
    setPages(descs);
    setOverlays({});
    setTextEdits([]);
    const firstId = descs[0]?.pageId ?? "";
    setCurrentEditingPageId(firstId);
    setSelectedPageIds(new Set(firstId ? [firstId] : []));
    lastClickedRef.current = firstId;
    undoStack.current = [];
    undoPointer.current = -1;
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  const reset = useCallback(() => {
    setPages([]);
    setOverlays({});
    setTextEdits([]);
    setCurrentEditingPageId("");
    setSelectedPageIds(new Set());
    undoStack.current = [];
    undoPointer.current = -1;
    setCanUndo(false);
    setCanRedo(false);
    lastClickedRef.current = "";
  }, []);

  const setOverlay = useCallback((pageId: string, json: string) => {
    setOverlays((prev) => ({ ...prev, [pageId]: json }));
  }, []);

  const navigateTo = useCallback((pageId: string) => {
    setCurrentEditingPageId(pageId);
    setSelectedPageIds(new Set([pageId]));
    lastClickedRef.current = pageId;
  }, []);

  const selectOnly = useCallback((pageId: string) => {
    setSelectedPageIds(new Set([pageId]));
    lastClickedRef.current = pageId;
  }, []);

  const toggleSelect = useCallback((pageId: string) => {
    setSelectedPageIds((prev) => {
      const next = new Set(prev);
      if (next.has(pageId)) {
        next.delete(pageId);
      } else {
        next.add(pageId);
        lastClickedRef.current = pageId;
      }
      return next;
    });
  }, []);

  const rangeSelect = useCallback((toPageId: string) => {
    const current = pagesRef.current;
    const anchorId = lastClickedRef.current;
    const aIdx = current.findIndex((p) => p.pageId === anchorId);
    const bIdx = current.findIndex((p) => p.pageId === toPageId);
    if (aIdx < 0 || bIdx < 0) {
      setSelectedPageIds(new Set([toPageId]));
      return;
    }
    const lo = Math.min(aIdx, bIdx);
    const hi = Math.max(aIdx, bIdx);
    setSelectedPageIds(new Set(current.slice(lo, hi + 1).map((p) => p.pageId)));
  }, []);

  const selectAll = useCallback(() => {
    setSelectedPageIds(new Set(pagesRef.current.map((p) => p.pageId)));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedPageIds(new Set());
  }, []);

  const rotatePagesCmd = useCallback(
    (pageIds: string[], direction: "cw" | "ccw", scale: number) => {
      const delta: 90 | 270 = direction === "cw" ? 90 : 270;
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;

      const newPages = current.map((p) => {
        if (!pageIds.includes(p.pageId)) return p;
        const newRot = normalizeRotation(p.rotation + delta);
        // Swap width/height for 90/270 degree rotation
        return {
          ...p,
          rotation: newRot,
          width: p.height,
          height: p.width,
        };
      });

      const newOverlays = { ...currentOverlays };
      for (const pageId of pageIds) {
        const json = currentOverlays[pageId];
        if (!json) continue;
        const p = current.find((pg) => pg.pageId === pageId);
        if (!p) continue;
        newOverlays[pageId] = transformOverlayForRotation(
          json,
          p.width * scale,
          p.height * scale,
          delta
        );
      }

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: textEditsRef.current },
        { pages: newPages, overlays: newOverlays, textEdits: textEditsRef.current },
        `Rotate ${pageIds.length > 1 ? `${pageIds.length} pages` : "page"} ${direction === "cw" ? "CW" : "CCW"}`
      );
    },
    [pushCommand]
  );

  const deletePagesCmd = useCallback(
    (pageIds: string[]) => {
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;
      const idSet = new Set(pageIds);

      const newPages = current.filter((p) => !idSet.has(p.pageId));
      const newOverlays = Object.fromEntries(
        Object.entries(currentOverlays).filter(([id]) => !idSet.has(id))
      );

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: textEditsRef.current },
        { pages: newPages, overlays: newOverlays, textEdits: textEditsRef.current },
        `Delete ${pageIds.length} page(s)`
      );

      // If current editing page was deleted, navigate to nearest surviving page
      setCurrentEditingPageId((prev) => {
        if (!idSet.has(prev)) return prev;
        // Find the page just before the deleted range
        const deletedIdxs = pageIds.map((id) => current.findIndex((p) => p.pageId === id));
        const minDeleted = Math.min(...deletedIdxs);
        const fallback = newPages[Math.max(0, minDeleted - 1)] ?? newPages[0];
        return fallback?.pageId ?? "";
      });
      setSelectedPageIds(new Set());
    },
    [pushCommand]
  );

  const reorderPagesCmd = useCallback(
    (activeId: string, overId: string) => {
      if (activeId === overId) return;
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;

      const fromIdx = current.findIndex((p) => p.pageId === activeId);
      const toIdx = current.findIndex((p) => p.pageId === overId);
      if (fromIdx < 0 || toIdx < 0) return;

      const newPages = [...current];
      const [moved] = newPages.splice(fromIdx, 1);
      newPages.splice(toIdx, 0, moved);

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: textEditsRef.current },
        { pages: newPages, overlays: currentOverlays, textEdits: textEditsRef.current },
        "Reorder pages"
      );
    },
    [pushCommand]
  );

  const duplicatePagesCmd = useCallback(
    (pageIds: string[]) => {
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;
      const idSet = new Set(pageIds);

      const newPages: PageDescriptor[] = [];
      const newOverlays = { ...currentOverlays };

      for (const p of current) {
        newPages.push(p);
        if (idSet.has(p.pageId)) {
          const newId = makePageId("dup");
          newPages.push({ ...p, pageId: newId });
          if (currentOverlays[p.pageId]) {
            newOverlays[newId] = currentOverlays[p.pageId];
          }
        }
      }

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: textEditsRef.current },
        { pages: newPages, overlays: newOverlays, textEdits: textEditsRef.current },
        `Duplicate ${pageIds.length} page(s)`
      );
    },
    [pushCommand]
  );

  const insertBlankCmd = useCallback(
    (afterPageId: string) => {
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;
      const insertAfterIdx = current.findIndex((p) => p.pageId === afterPageId);
      const dims = blankPageDims(current, insertAfterIdx);

      const blank: PageDescriptor = {
        pageId: makePageId("blank"),
        sourceIndex: -1,
        rotation: 0,
        isBlank: true,
        width: dims.width,
        height: dims.height,
      };

      const newPages = [...current];
      newPages.splice(insertAfterIdx + 1, 0, blank);

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: textEditsRef.current },
        { pages: newPages, overlays: currentOverlays, textEdits: textEditsRef.current },
        "Insert blank page"
      );
    },
    [pushCommand]
  );

  const textEditCmd = useCallback(
    (entry: TextEditEntry) => {
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;
      const currentEdits = textEditsRef.current;

      // Upsert: replace existing edit for same spanIds, else append
      const spanKey = entry.spanIds.join(",");
      const newEdits = currentEdits.filter(
        (e) => e.spanIds.join(",") !== spanKey
      );
      newEdits.push(entry);

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: currentEdits },
        { pages: current, overlays: currentOverlays, textEdits: newEdits },
        "Edit text"
      );
    },
    [pushCommand]
  );

  const bulkTextEditCmd = useCallback(
    (entries: TextEditEntry[], label = "Replace text") => {
      const current = pagesRef.current;
      const currentOverlays = overlaysRef.current;
      const currentEdits = textEditsRef.current;

      const newEdits = [...currentEdits];
      for (const entry of entries) {
        const spanKey = entry.spanIds.join(",");
        const idx = newEdits.findIndex((e) => e.spanIds.join(",") === spanKey);
        if (idx >= 0) {
          newEdits[idx] = entry;
        } else {
          newEdits.push(entry);
        }
      }

      pushCommand(
        { pages: current, overlays: currentOverlays, textEdits: currentEdits },
        { pages: current, overlays: currentOverlays, textEdits: newEdits },
        label
      );
    },
    [pushCommand]
  );

  const overlayChangeCmd = useCallback(
    (pageId: string, beforeJSON: string, afterJSON: string, label: string) => {
      const current = pagesRef.current;
      const currentEdits = textEditsRef.current;
      const baseOverlays = overlaysRef.current;
      pushCommand(
        { pages: current, overlays: { ...baseOverlays, [pageId]: beforeJSON }, textEdits: currentEdits },
        { pages: current, overlays: { ...baseOverlays, [pageId]: afterJSON }, textEdits: currentEdits },
        label
      );
    },
    [pushCommand]
  );

  const clearTextEdits = useCallback(() => {
    const current = pagesRef.current;
    const currentOverlays = overlaysRef.current;
    const currentEdits = textEditsRef.current;
    if (currentEdits.length === 0) return;
    pushCommand(
      { pages: current, overlays: currentOverlays, textEdits: currentEdits },
      { pages: current, overlays: currentOverlays, textEdits: [] },
      "Clear text edits"
    );
  }, [pushCommand]);

  return {
    pages,
    overlays,
    textEdits,
    currentEditingPageId,
    selectedPageIds,
    canUndo,
    canRedo,
    initFromDoc,
    setOverlay,
    navigateTo,
    selectOnly,
    toggleSelect,
    rangeSelect,
    selectAll,
    clearSelection,
    rotatePagesCmd,
    deletePagesCmd,
    reorderPagesCmd,
    duplicatePagesCmd,
    insertBlankCmd,
    textEditCmd,
    bulkTextEditCmd,
    clearTextEdits,
    overlayChangeCmd,
    undo,
    redo,
    reset,
  };
}
