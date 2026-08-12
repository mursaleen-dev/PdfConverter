"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageDescriptor } from "./types";

interface ThumbnailItemProps {
  descriptor: PageDescriptor;
  index: number;
  pdfDoc: PDFDocumentProxy | null;
  thumbCache: React.MutableRefObject<Map<string, string>>;
  isSelected: boolean;
  isEditing: boolean;
  onNavigate: (pageId: string) => void;
  onSelect: (pageId: string, e: React.MouseEvent) => void;
  /** Renders drag handle and sortable attributes via render-prop children */
  dragHandle?: React.ReactNode;
  style?: React.CSSProperties;
}

const THUMB_W = 90;

export default function ThumbnailItem({
  descriptor,
  index,
  pdfDoc,
  thumbCache,
  isSelected,
  isEditing,
  onNavigate,
  onSelect,
  dragHandle,
  style,
}: ThumbnailItemProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dataUrl, setDataUrl] = useState<string | null>(null);

  const cacheKey = descriptor.isBlank
    ? `blank_${descriptor.width}x${descriptor.height}`
    : `src${descriptor.sourceIndex}_r${descriptor.rotation}`;

  useEffect(() => {
    const cached = thumbCache.current.get(cacheKey);
    if (cached) { setDataUrl(cached); return; }

    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;

    const render = async () => {
      if (descriptor.isBlank) {
        // White rectangle at thumbnail aspect ratio
        const aspect = descriptor.height > 0 ? descriptor.width / descriptor.height : 0.707;
        const w = THUMB_W;
        const h = Math.round(w / aspect);
        const offscreen = document.createElement("canvas");
        offscreen.width = w;
        offscreen.height = h;
        const ctx = offscreen.getContext("2d")!;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = "#d1d5db";
        ctx.strokeRect(0, 0, w, h);
        const url = offscreen.toDataURL("image/png");
        if (!cancelled) { thumbCache.current.set(cacheKey, url); setDataUrl(url); }
        return;
      }

      if (!pdfDoc) return;
      try {
        const page = await pdfDoc.getPage(descriptor.sourceIndex + 1);
        const vp0 = page.getViewport({ scale: 1, rotation: descriptor.rotation });
        const thumbScale = THUMB_W / vp0.width;
        const vp = page.getViewport({ scale: thumbScale, rotation: descriptor.rotation });
        const offscreen = document.createElement("canvas");
        offscreen.width = vp.width;
        offscreen.height = vp.height;
        const ctx = offscreen.getContext("2d")!;
        const task = page.render({ canvasContext: ctx, viewport: vp, intent: "print" } as Parameters<typeof page.render>[0]);
        await task.promise;
        if (!cancelled) {
          const url = offscreen.toDataURL("image/png");
          thumbCache.current.set(cacheKey, url);
          setDataUrl(url);
        }
      } catch {
        // Render failed — leave dataUrl null (shows placeholder)
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          observer.disconnect();
          render();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(container);
    return () => { cancelled = true; observer.disconnect(); };
  }, [cacheKey, descriptor, pdfDoc, thumbCache]);

  const aspect = descriptor.height > 0 ? descriptor.height / descriptor.width : 1.414;
  const thumbH = Math.round(THUMB_W * aspect);

  return (
    <div
      ref={containerRef}
      style={style}
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey) {
          onSelect(descriptor.pageId, e);
        } else {
          onNavigate(descriptor.pageId);
        }
      }}
      className={[
        "group relative flex flex-col items-center gap-1 cursor-pointer rounded-lg p-1 select-none",
        isSelected ? "bg-blue-100 dark:bg-blue-900/40" : "hover:bg-neutral-100 dark:hover:bg-neutral-800",
        isEditing ? "ring-2 ring-blue-500 rounded-lg" : "",
      ].join(" ")}
    >
      {dragHandle && (
        <div className="absolute top-0.5 left-0.5 opacity-0 group-hover:opacity-60 transition-opacity z-10">
          {dragHandle}
        </div>
      )}

      {/* Thumbnail image or placeholder */}
      <div
        className="relative overflow-hidden rounded border border-neutral-200 bg-white shadow-sm dark:border-neutral-700"
        style={{ width: THUMB_W, height: thumbH }}
      >
        {dataUrl ? (
          <img
            src={dataUrl}
            alt={`Page ${index + 1}`}
            className="h-full w-full object-contain"
            draggable={false}
          />
        ) : (
          <div className="h-full w-full animate-pulse bg-neutral-100 dark:bg-neutral-800" />
        )}
      </div>

      {/* Page number label */}
      <span className="text-[10px] leading-tight text-neutral-500 dark:text-neutral-400">
        {index + 1}
      </span>
    </div>
  );
}
