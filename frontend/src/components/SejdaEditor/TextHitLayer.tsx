"use client";

import { useCallback, useState } from "react";
import type { ExtractedLine, ExtractedParagraph, ExtractedSpan, PageRotation } from "./types";

interface TextHitLayerProps {
  paragraphs: ExtractedParagraph[];
  pageWidth: number;    // original page width in PDF points
  pageHeight: number;   // original page height in PDF points
  scale: number;        // render scale (pixels per PDF point)
  userRotation: PageRotation;
  onParaClick: (para: ExtractedParagraph) => void;
  onSpanClick: (para: ExtractedParagraph, span: ExtractedSpan) => void;
  activeParagraphId?: string;
}

type Granularity = "para" | "span";

/**
 * Transform a PDF-space point to canvas-pixel coordinates.
 * Matches the pdfjs getViewport({ scale, rotation: userRotation }) transform.
 */
function pdfToCanvas(
  px: number,
  py: number,
  pageW: number,
  pageH: number,
  rotation: PageRotation,
  scale: number
): { x: number; y: number } {
  switch (rotation) {
    case 0:   return { x: px * scale, y: py * scale };
    case 90:  return { x: (pageH - py) * scale, y: px * scale };
    case 180: return { x: (pageW - px) * scale, y: (pageH - py) * scale };
    case 270: return { x: py * scale, y: (pageW - px) * scale };
  }
}

function bboxToHitRect(
  bbox: [number, number, number, number],
  pageW: number,
  pageH: number,
  rotation: PageRotation,
  scale: number
): { left: number; top: number; width: number; height: number } {
  const [x0, y0, x1, y1] = bbox;
  const corners = [
    pdfToCanvas(x0, y0, pageW, pageH, rotation, scale),
    pdfToCanvas(x1, y0, pageW, pageH, rotation, scale),
    pdfToCanvas(x0, y1, pageW, pageH, rotation, scale),
    pdfToCanvas(x1, y1, pageW, pageH, rotation, scale),
  ];
  const xs = corners.map((c) => c.x);
  const ys = corners.map((c) => c.y);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  return {
    left,
    top,
    width: Math.max(...xs) - left,
    height: Math.max(...ys) - top,
  };
}

const DEBUG_TEXT_LAYER = false;
const MIN_TOUCH_TARGET = 44;

export default function TextHitLayer({
  paragraphs,
  pageWidth,
  pageHeight,
  scale,
  userRotation,
  onParaClick,
  onSpanClick,
  activeParagraphId,
}: TextHitLayerProps) {
  const [granularity, setGranularity] = useState<Granularity>("para");

  const handleLineClick = useCallback(
    (e: React.MouseEvent, para: ExtractedParagraph, line: ExtractedLine) => {
      if (e.altKey || granularity === "span") {
        // Alt-click or span-mode: find nearest span within this line only
        const canvasX = e.nativeEvent.offsetX;
        const canvasY = e.nativeEvent.offsetY;
        let nearestSpan: ExtractedSpan | null = null;
        let nearestDist = Infinity;
        for (const span of line.spans) {
          if (!span.isLtr) continue;
          const r = bboxToHitRect(span.bbox, pageWidth, pageHeight, userRotation, scale);
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          const d = Math.hypot(canvasX - cx, canvasY - cy);
          if (d < nearestDist) {
            nearestDist = d;
            nearestSpan = span;
          }
        }
        if (nearestSpan) onSpanClick(para, nearestSpan);
      } else {
        onParaClick(para);
      }
    },
    [onParaClick, onSpanClick, pageWidth, pageHeight, userRotation, scale, granularity]
  );

  const handleLineDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setGranularity((g) => (g === "para" ? "span" : "para"));
    },
    []
  );

  // Only keep paragraphs that have at least one LTR span
  const editableParagraphs = paragraphs.filter((p) =>
    p.lines.some((l) => l.spans.some((s) => s.isLtr))
  );

  return (
    <div
      className="pointer-events-none absolute inset-0"
      aria-hidden="true"
      style={DEBUG_TEXT_LAYER ? { outline: "2px solid lime" } : undefined}
    >
      {/* Granularity badge — click to toggle between paragraph and span mode */}
      <div
        className="pointer-events-auto absolute right-0 top-0 z-10 cursor-pointer select-none rounded-bl-md bg-blue-600 px-1.5 py-0.5 text-[10px] font-semibold text-white"
        onClick={() => setGranularity((g) => (g === "para" ? "span" : "para"))}
        title="Click to toggle: paragraph or span selection mode (also: double-click any text)"
      >
        {granularity === "para" ? "¶ Para" : "◆ Span"}
      </div>

      {editableParagraphs.map((para) => {
        // Filter to lines that have at least one LTR span
        const editableLines = para.lines.filter((l) => l.spans.some((s) => s.isLtr));
        if (editableLines.length === 0) return null;

        const isActive = para.paraId === activeParagraphId;

        // Compute canvas rect for each editable line
        const lineRects = editableLines.map((line) =>
          bboxToHitRect(line.bbox, pageWidth, pageHeight, userRotation, scale)
        );

        return (
          <span key={para.paraId}>
            {editableLines.map((line, li) => {
              const r = lineRects[li];
              const center = r.top + r.height / 2;

              // Territory: split midpoint with adjacent lines (non-overlapping)
              const topBound =
                li === 0
                  ? r.top
                  : (lineRects[li - 1].top + lineRects[li - 1].height / 2 + center) / 2;

              const bottomBound =
                li === editableLines.length - 1
                  ? r.top + r.height
                  : (center + lineRects[li + 1].top + lineRects[li + 1].height / 2) / 2;

              // Enforce 44 px minimum touch target (expand symmetrically)
              let tTop = topBound;
              let tHeight = bottomBound - topBound;
              if (tHeight < MIN_TOUCH_TARGET) {
                const extra = (MIN_TOUCH_TARGET - tHeight) / 2;
                tTop -= extra;
                tHeight = MIN_TOUCH_TARGET;
              }

              return (
                <div
                  key={`${para.paraId}:${li}`}
                  className={[
                    "absolute cursor-text pointer-events-auto rounded-sm border transition-colors",
                    isActive
                      ? "border-blue-500 bg-blue-50/10"
                      : "border-transparent hover:border-blue-400/60 hover:bg-blue-50/5",
                  ].join(" ")}
                  style={{
                    left: r.left,
                    top: tTop,
                    width: r.width,
                    height: tHeight,
                    ...(DEBUG_TEXT_LAYER
                      ? { outline: "1px solid red", background: "rgba(255,0,0,0.12)" }
                      : {}),
                  }}
                  onClick={(e) => handleLineClick(e, para, line)}
                  onDoubleClick={handleLineDoubleClick}
                  title={
                    granularity === "para"
                      ? "Click to edit paragraph · Alt+click for single span · Double-click for span mode"
                      : "Click to edit span · Double-click for paragraph mode"
                  }
                />
              );
            })}
          </span>
        );
      })}
    </div>
  );
}
