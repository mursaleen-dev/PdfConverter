"use client";

import { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import type { PDFPageProxy } from "pdfjs-dist";
import {
  Canvas as FabricCanvas,
  IText,
  Rect,
  Ellipse,
  Path,
  FabricImage,
  FabricObject,
  PencilBrush,
} from "fabric";
import type { ActiveTool, PageRotation, ToolSettings } from "./types";

export interface SelectionBounds {
  left: number;
  top: number;
  width: number;
  height: number;
  count: number;
}

export interface FabricPageHandle {
  getJSON: () => string;
  loadJSON: (json: string) => void;
  addImageFromDataUrl: (dataUrl: string, fabricType?: string) => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
  bringForward: () => void;
  sendBackward: () => void;
  isTextEditing: () => boolean;
}

interface FabricPageProps {
  pdfPage: PDFPageProxy;
  scale: number;
  userRotation: PageRotation;
  activeTool: ActiveTool;
  toolSettings: ToolSettings;
  initialJSON?: string;
  /** Called on every canvas mutation for live state sync (non-undoable). */
  onStateChange: (json: string) => void;
  /** Called at the end of each user gesture for undo stack. */
  onUndoableChange: (beforeJSON: string, afterJSON: string, label: string) => void;
  /** Fires whenever Fabric selection changes. null = nothing selected. */
  onSelectionChange?: (bounds: SelectionBounds | null) => void;
  /** Fires on right-click over a selected object. Coords are screen pixels. */
  onContextMenu?: (screenX: number, screenY: number) => void;
}

const CUSTOM_PROPS = ["data"];

function getSelectionBounds(fc: FabricCanvas): SelectionBounds | null {
  const objs = fc.getActiveObjects();
  if (!objs.length) return null;
  const active = fc.getActiveObject();
  if (!active) return null;
  const b = active.getBoundingRect();
  return { left: b.left, top: b.top, width: b.width, height: b.height, count: objs.length };
}

const FabricPage = forwardRef<FabricPageHandle, FabricPageProps>(function FabricPage(
  {
    pdfPage,
    scale,
    userRotation,
    activeTool,
    toolSettings,
    initialJSON,
    onStateChange,
    onUndoableChange,
    onSelectionChange,
    onContextMenu,
  },
  ref
) {
  const pdfCanvasRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<HTMLCanvasElement>(null);
  const fcRef = useRef<FabricCanvas | null>(null);
  const activeToolRef = useRef(activeTool);
  const settingsRef = useRef(toolSettings);
  const rawPointsRef = useRef<{ x: number; y: number }[]>([]);
  const drawingRef = useRef<{
    shape: Rect | Ellipse | null;
    startX: number;
    startY: number;
    shapeType: string;
  } | null>(null);
  const pointerDownRef = useRef(false);
  // Snapshot of canvas JSON captured at the START of each user gesture.
  const beforeSnapshotRef = useRef("");
  // Snapshot captured when IText enters editing (covers both new and existing text edits).
  const textEditBeforeRef = useRef("");

  useEffect(() => { activeToolRef.current = activeTool; }, [activeTool]);
  useEffect(() => { settingsRef.current = toolSettings; }, [toolSettings]);

  // ── Render PDF page to background canvas ──────────────────────────────────
  useEffect(() => {
    const canvas = pdfCanvasRef.current;
    if (!canvas) return;
    const viewport = pdfPage.getViewport({ scale, rotation: userRotation });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d")!;
    const task = pdfPage.render({ canvasContext: ctx, viewport, intent: "print" } as Parameters<typeof pdfPage.render>[0]);
    return () => { task.cancel(); };
  }, [pdfPage, scale, userRotation]);

  // ── Fabric canvas lifecycle ────────────────────────────────────────────────
  useEffect(() => {
    const viewport = pdfPage.getViewport({ scale, rotation: userRotation });
    const w = viewport.width;
    const h = viewport.height;

    const fc = new FabricCanvas(fabricCanvasRef.current!, {
      width: w,
      height: h,
      selection: true,
      preserveObjectStacking: true,
      stopContextMenu: false, // we handle context menu ourselves
    });
    fcRef.current = fc;

    if (initialJSON) {
      try {
        fc.loadFromJSON(JSON.parse(initialJSON)).then(() => fc.requestRenderAll()).catch(() => {});
      } catch { /* corrupt JSON — start fresh */ }
    }

    /** Push live state to parent (non-undoable). */
    const notifyLive = () => {
      onStateChange(JSON.stringify(fc.toObject(CUSTOM_PROPS)));
    };

    /** Capture current JSON as the "before" for an upcoming gesture. */
    const captureBeforeSnapshot = () => {
      beforeSnapshotRef.current = JSON.stringify(fc.toObject(CUSTOM_PROPS));
    };

    /** Push undoable command: before was already captured in beforeSnapshotRef. */
    const commitUndoable = (label: string) => {
      const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      notifyLive(); // keep parent overlay state fresh
      onUndoableChange(beforeSnapshotRef.current, after, label);
    };

    // ── Shape drawing ──────────────────────────────────────────────────────
    fc.on("mouse:down", (opt) => {
      pointerDownRef.current = true;
      captureBeforeSnapshot(); // always capture before any gesture

      const tool = activeToolRef.current;
      const s = settingsRef.current;
      const p = opt.absolutePointer ?? opt.pointer;
      if (!p) return;

      if (tool === "freehand") {
        rawPointsRef.current = [{ x: p.x, y: p.y }];
        return;
      }

      if (tool === "eraser") {
        const active = fc.getActiveObjects();
        if (active.length) {
          active.forEach((o) => fc.remove(o));
          fc.discardActiveObject();
          fc.requestRenderAll();
          commitUndoable("Erase");
        }
        return;
      }

      const shapeTools = ["rect", "ellipse", "highlight", "strikethrough", "whiteout"];
      if (!shapeTools.includes(tool)) return;

      const fill =
        tool === "highlight" ? "#facc15"
        : tool === "strikethrough" ? "transparent"
        : tool === "whiteout" ? "#ffffff"
        : s.fillColor === "transparent" ? "transparent"
        : s.fillColor;

      const stroke =
        tool === "highlight" ? "transparent"
        : tool === "strikethrough" ? s.strokeColor
        : tool === "whiteout" ? "#ffffff"
        : s.strokeColor;

      const opacity =
        tool === "highlight" ? 0.4
        : tool === "strikethrough" ? 1
        : tool === "whiteout" ? 1
        : s.opacity;

      let shape: Rect | Ellipse;
      if (tool === "ellipse") {
        shape = new Ellipse({
          left: p.x, top: p.y, rx: 0, ry: 0,
          fill, stroke, strokeWidth: s.strokeWidth,
          opacity, selectable: false, evented: false,
          data: { fabricType: tool },
        });
      } else {
        shape = new Rect({
          left: p.x, top: p.y, width: 0, height: 0,
          fill, stroke, strokeWidth: s.strokeWidth,
          opacity, selectable: false, evented: false,
          data: { fabricType: tool },
        });
      }

      fc.add(shape);
      drawingRef.current = { shape, startX: p.x, startY: p.y, shapeType: tool };
    });

    fc.on("mouse:move", (opt) => {
      if (!pointerDownRef.current) return;
      const p = opt.absolutePointer ?? opt.pointer;
      if (!p) return;

      if (activeToolRef.current === "freehand") {
        rawPointsRef.current.push({ x: p.x, y: p.y });
        return;
      }

      const d = drawingRef.current;
      if (!d?.shape) return;

      const x = Math.min(p.x, d.startX);
      const y = Math.min(p.y, d.startY);
      const dw = Math.abs(p.x - d.startX);
      const dh = Math.abs(p.y - d.startY);

      if (d.shape instanceof Ellipse) {
        d.shape.set({ left: x, top: y, rx: dw / 2, ry: dh / 2 });
      } else {
        d.shape.set({ left: x, top: y, width: dw, height: dh });
      }
      fc.requestRenderAll();
    });

    fc.on("mouse:up", () => {
      pointerDownRef.current = false;
      const d = drawingRef.current;
      if (d?.shape) {
        const tooSmall = d.shape instanceof Ellipse
          ? (d.shape.rx ?? 0) < 3
          : (d.shape.width ?? 0) < 3;
        if (tooSmall) {
          fc.remove(d.shape);
        } else {
          d.shape.set({ selectable: true, evented: true });
          fc.setActiveObject(d.shape);
          commitUndoable(`Draw ${d.shapeType}`);
        }
        drawingRef.current = null;
      }
    });

    // ── Object drag/resize: push undo entry on gesture end ─────────────────
    fc.on("object:modified", () => {
      commitUndoable("Move");
    });

    // ── Text click-to-place ────────────────────────────────────────────────
    fc.on("mouse:down", (opt) => {
      if (activeToolRef.current !== "text") return;
      const p = opt.absolutePointer ?? opt.pointer;
      if (!p) return;
      // before-snapshot already captured at top of mouse:down
      const s = settingsRef.current;

      const t = new IText("Text", {
        left: p.x,
        top: p.y,
        fontSize: s.fontSize,
        fontFamily: s.fontFamily,
        fontWeight: s.bold ? "bold" : "normal",
        fontStyle: s.italic ? "italic" : "normal",
        underline: s.underline,
        fill: s.textColor,
        data: { fabricType: "text" },
      });
      fc.add(t);
      fc.setActiveObject(t);
      t.enterEditing();
      t.selectAll();
      notifyLive();
    });

    // Capture state just before entering IText editing (handles both new and existing text).
    fc.on("text:editing:entered", () => {
      textEditBeforeRef.current = beforeSnapshotRef.current;
    });

    // When editing exits, push one undo entry for the entire typed content.
    fc.on("text:editing:exited", () => {
      const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      notifyLive();
      onUndoableChange(textEditBeforeRef.current || beforeSnapshotRef.current, after, "Edit text");
    });

    // ── Freehand path ──────────────────────────────────────────────────────
    fc.on("path:created", (e: { path: Path }) => {
      const path = e.path;
      const pts = rawPointsRef.current.slice();
      rawPointsRef.current = [];
      path.set({ data: { fabricType: "freehand", rawPoints: pts } });
      commitUndoable("Draw");
    });

    // Live state sync for object:added (e.g. image added programmatically) —
    // undoable entry pushed separately by addImageFromDataUrl.
    fc.on("object:added", notifyLive);
    fc.on("object:removed", notifyLive);

    // ── Selection tracking ─────────────────────────────────────────────────
    const emitSelection = () => {
      onSelectionChange?.(getSelectionBounds(fc));
    };
    fc.on("selection:created", emitSelection);
    fc.on("selection:updated", emitSelection);
    fc.on("selection:cleared", () => onSelectionChange?.(null));
    // Reposition toolbar when selected object moves/resizes
    fc.on("object:modified", emitSelection);

    // ── Right-click context menu ───────────────────────────────────────────
    const handleContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      if (fc.getActiveObjects().length && onContextMenu) {
        onContextMenu(e.clientX, e.clientY);
      }
    };
    fc.wrapperEl.addEventListener("contextmenu", handleContextMenu);

    // ── Delete / Backspace key ─────────────────────────────────────────────
    const isEditingText = () => {
      const target = document.activeElement;
      if (target instanceof HTMLInputElement) return true;
      if (target instanceof HTMLTextAreaElement) return true;
      if (target instanceof HTMLElement && target.isContentEditable) return true;
      const active = fc.getActiveObject() as (IText & { isEditing?: boolean }) | null;
      return !!active?.isEditing;
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      if (isEditingText()) return;
      const active = fc.getActiveObjects();
      if (!active.length) return;
      captureBeforeSnapshot();
      active.forEach((o) => fc.remove(o));
      fc.discardActiveObject();
      fc.requestRenderAll();
      commitUndoable("Delete");
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      fc.wrapperEl.removeEventListener("contextmenu", handleContextMenu);
      fc.dispose();
      fcRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount-only — tool/settings via refs, parent callbacks via closure refresh below

  // Keep parent callbacks fresh inside the mount-only closure via a ref trampoline.
  const onStateChangeRef = useRef(onStateChange);
  const onUndoableChangeRef = useRef(onUndoableChange);
  const onSelectionChangeRef = useRef(onSelectionChange);
  const onContextMenuRef = useRef(onContextMenu);
  useEffect(() => { onStateChangeRef.current = onStateChange; }, [onStateChange]);
  useEffect(() => { onUndoableChangeRef.current = onUndoableChange; }, [onUndoableChange]);
  useEffect(() => { onSelectionChangeRef.current = onSelectionChange; }, [onSelectionChange]);
  useEffect(() => { onContextMenuRef.current = onContextMenu; }, [onContextMenu]);

  // ── Sync active tool → Fabric behaviour ───────────────────────────────────
  useEffect(() => {
    const fc = fcRef.current;
    if (!fc) return;

    fc.isDrawingMode = activeTool === "freehand";
    fc.selection = activeTool === "select";

    // In edit-text mode Fabric must be completely inert so clicks reach TextHitLayer.
    fc.wrapperEl.style.pointerEvents = activeTool === "edit-text" ? "none" : "";

    if (activeTool === "freehand") {
      const brush = new PencilBrush(fc);
      brush.color = toolSettings.freehandColor;
      brush.width = toolSettings.freehandWidth;
      brush.decimate = 2;
      fc.freeDrawingBrush = brush;
    }

    const shapeOrTextTools = ["rect", "ellipse", "highlight", "strikethrough", "whiteout", "text"];
    fc.defaultCursor = shapeOrTextTools.includes(activeTool) ? "crosshair" : "default";
  }, [activeTool, toolSettings.freehandColor, toolSettings.freehandWidth]);

  // ── Sync freehand brush settings on change ────────────────────────────────
  useEffect(() => {
    const fc = fcRef.current;
    if (!fc?.freeDrawingBrush) return;
    fc.freeDrawingBrush.color = toolSettings.freehandColor;
    fc.freeDrawingBrush.width = toolSettings.freehandWidth;
  }, [toolSettings.freehandColor, toolSettings.freehandWidth]);

  // ── Imperative handle ─────────────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    getJSON() {
      return fcRef.current
        ? JSON.stringify(fcRef.current.toObject(CUSTOM_PROPS))
        : "{}";
    },

    loadJSON(json: string) {
      const fc = fcRef.current;
      if (!fc) return;
      try {
        fc.loadFromJSON(JSON.parse(json)).then(() => {
          fc.requestRenderAll();
          onSelectionChange?.(null);
        }).catch(() => {});
      } catch { /* invalid json */ }
    },

    addImageFromDataUrl(dataUrl: string, fabricType = "image") {
      const fc = fcRef.current;
      if (!fc) return;
      const before = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      FabricImage.fromURL(dataUrl).then((img) => {
        const maxW = fc.width! * 0.5;
        if (img.width! > maxW) img.scale(maxW / img.width!);
        img.set({
          left: fc.width! / 2 - (img.width! * (img.scaleX ?? 1)) / 2,
          top: fc.height! / 2 - (img.height! * (img.scaleY ?? 1)) / 2,
          data: { fabricType, imageData: dataUrl },
        });
        fc.add(img);
        fc.setActiveObject(img);
        fc.requestRenderAll();
        const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
        onStateChange(after);
        onUndoableChange(before, after, "Add image");
      });
    },

    deleteSelected() {
      const fc = fcRef.current;
      if (!fc) return;
      const active = fc.getActiveObjects();
      if (!active.length) return;
      const before = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      active.forEach((o) => fc.remove(o));
      fc.discardActiveObject();
      fc.requestRenderAll();
      const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      onStateChange(after);
      onUndoableChange(before, after, "Delete");
      onSelectionChange?.(null);
    },

    duplicateSelected() {
      const fc = fcRef.current;
      if (!fc) return;
      const active = fc.getActiveObjects();
      if (!active.length) return;
      const before = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      const OFFSET = 16;
      Promise.all(active.map((o) => o.clone())).then((clones) => {
        fc.discardActiveObject();
        clones.forEach((c: FabricObject) => {
          c.set({ left: (c.left ?? 0) + OFFSET, top: (c.top ?? 0) + OFFSET });
          fc.add(c);
        });
        fc.requestRenderAll();
        const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
        onStateChange(after);
        onUndoableChange(before, after, "Duplicate");
      });
    },

    bringForward() {
      const fc = fcRef.current;
      if (!fc) return;
      const objs = fc.getActiveObjects();
      if (!objs.length) return;
      const before = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      objs.forEach((o) => fc.bringObjectForward(o));
      fc.requestRenderAll();
      const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      onStateChange(after);
      onUndoableChange(before, after, "Bring forward");
    },

    sendBackward() {
      const fc = fcRef.current;
      if (!fc) return;
      const objs = fc.getActiveObjects();
      if (!objs.length) return;
      const before = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      objs.forEach((o) => fc.sendObjectBackwards(o));
      fc.requestRenderAll();
      const after = JSON.stringify(fc.toObject(CUSTOM_PROPS));
      onStateChange(after);
      onUndoableChange(before, after, "Send backward");
    },

    isTextEditing() {
      const active = fcRef.current?.getActiveObject() as (IText & { isEditing?: boolean }) | null;
      return !!active?.isEditing;
    },
  }));

  const viewport = pdfPage.getViewport({ scale, rotation: userRotation });

  return (
    <div
      className="relative mx-auto bg-white shadow-lg"
      style={{ width: viewport.width, height: viewport.height }}
    >
      {/* PDF render layer */}
      <canvas
        ref={pdfCanvasRef}
        className="absolute inset-0"
        style={{ pointerEvents: "none" }}
      />
      {/* Fabric interactive layer */}
      <canvas ref={fabricCanvasRef} className="absolute inset-0" />
    </div>
  );
});

export default FabricPage;

/**
 * Convert all objects on a Fabric canvas JSON (one page) into ManifestObjects.
 * Called at save time from SejdaEditor.
 */
export function fabricJSONToManifest(
  pageJSON: { objects?: unknown[] } | undefined,
  pageId: string,
  scale: number
): import("./types").ManifestObject[] {
  if (!pageJSON?.objects) return [];
  const results: import("./types").ManifestObject[] = [];

  for (const raw of pageJSON.objects) {
    const obj = raw as Record<string, unknown>;
    const data = (obj.data ?? {}) as Record<string, unknown>;
    const fabricType = (data.fabricType as string | undefined) ?? obj.type;

    const left = (obj.left as number) ?? 0;
    const top = (obj.top as number) ?? 0;
    const scaleX = (obj.scaleX as number) ?? 1;
    const scaleY = (obj.scaleY as number) ?? 1;
    const rotation = (obj.angle as number) ?? 0;

    let w: number, h: number;
    if (obj.type === "ellipse") {
      w = ((obj.rx as number) ?? 0) * 2 * scaleX;
      h = ((obj.ry as number) ?? 0) * 2 * scaleY;
    } else {
      w = ((obj.width as number) ?? 0) * scaleX;
      h = ((obj.height as number) ?? 0) * scaleY;
    }

    const x = left / scale;
    const y = top / scale;
    const width = w / scale;
    const height = h / scale;

    if (obj.type === "i-text" || obj.type === "textbox" || fabricType === "text") {
      const pdfFontSize = ((obj.fontSize as number) ?? 16) / scale;
      const textWidth = Math.max(width, 200);
      const textHeight = Math.max(height, pdfFontSize * 3);
      results.push({
        type: "text",
        pageId, x, y, width: textWidth, height: textHeight, rotation,
        text: (obj.text as string) ?? "",
        fontSize: pdfFontSize,
        fontFamily: mapFontFamily(obj.fontFamily as string),
        bold: (obj.fontWeight as string) === "bold",
        italic: (obj.fontStyle as string) === "italic",
        underline: (obj.underline as boolean) ?? false,
        color: (obj.fill as string) ?? "#000000",
      });
      continue;
    }

    if (obj.type === "image") {
      const imgData = (data.imageData as string | undefined) ?? (obj.src as string | undefined);
      if (!imgData) continue;
      results.push({
        type: fabricType === "signature" ? "signature" : "image",
        pageId, x, y, width, height, rotation,
        imageData: imgData,
      });
      continue;
    }

    if (obj.type === "rect") {
      const ft = fabricType as string;
      results.push({
        type: ft === "whiteout" ? "whiteout"
             : ft === "highlight" ? "highlight"
             : ft === "strikethrough" ? "strikethrough"
             : "rect",
        pageId, x, y, width, height, rotation,
        fillColor: noTransparent(obj.fill as string),
        strokeColor: noTransparent(obj.stroke as string),
        strokeWidth: ((obj.strokeWidth as number) ?? 1) / scale,
        fillOpacity: (obj.opacity as number) ?? 1,
      });
      continue;
    }

    if (obj.type === "ellipse") {
      results.push({
        type: "ellipse",
        pageId, x, y, width, height, rotation,
        fillColor: noTransparent(obj.fill as string),
        strokeColor: noTransparent(obj.stroke as string),
        strokeWidth: ((obj.strokeWidth as number) ?? 1) / scale,
        fillOpacity: (obj.opacity as number) ?? 1,
      });
      continue;
    }

    if (obj.type === "path") {
      const rawPoints = data.rawPoints as { x: number; y: number }[] | undefined;
      const points = rawPoints
        ? rawPoints.map((p) => ({ x: p.x / scale, y: p.y / scale }))
        : extractPathPoints(obj.path as unknown[][], left, top, scaleX, scaleY, scale);

      results.push({
        type: "freehand",
        pageId, x, y, width, height,
        strokeColor: (obj.stroke as string) ?? "#000000",
        strokeWidth: ((obj.strokeWidth as number) ?? 3) / scale,
        points,
      });
      continue;
    }
  }

  return results;
}

function mapFontFamily(family: string | undefined): string {
  if (!family) return "helv";
  const f = family.toLowerCase();
  if (f.includes("times")) return "tiro";
  if (f.includes("courier")) return "cour";
  return "helv";
}

function noTransparent(v: string | undefined): string | undefined {
  return v && v !== "transparent" ? v : undefined;
}

function extractPathPoints(
  pathCmds: unknown[][],
  left: number,
  top: number,
  scaleX: number,
  scaleY: number,
  scale: number
): { x: number; y: number }[] {
  if (!Array.isArray(pathCmds)) return [];
  const pts: { x: number; y: number }[] = [];
  for (const cmd of pathCmds) {
    const t = cmd[0] as string;
    if ((t === "M" || t === "L") && cmd.length >= 3) {
      pts.push({
        x: (left + (cmd[1] as number) * scaleX) / scale,
        y: (top + (cmd[2] as number) * scaleY) / scale,
      });
    } else if (t === "Q" && cmd.length >= 5) {
      pts.push({
        x: (left + (cmd[3] as number) * scaleX) / scale,
        y: (top + (cmd[4] as number) * scaleY) / scale,
      });
    }
  }
  return pts;
}
