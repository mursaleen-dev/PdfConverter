"use client";

import type { TextRun } from "./types";

export interface TextEditPreview {
  key: string;       // spanIds.join(",") — stable identity for the edit
  pageId: string;
  coverRect: [number, number, number, number];  // PDF coords [x0,y0,x1,y1], y-down
  insertX: number;   // PDF x origin for preview text
  insertY: number;   // PDF y for top of text area (= coverRect[1])
  runs: TextRun[];
  fontSize: number;  // dominant span size in PDF points
  backgroundColor: string;
}

interface Props {
  previews: TextEditPreview[];
  scale: number;
  pageWidth: number;
  pageHeight: number;
  userRotation: number;
}

function toCanvas(
  px: number,
  py: number,
  pageW: number,
  pageH: number,
  rotation: number,
  scale: number,
): { x: number; y: number } {
  switch (rotation) {
    case 90:  return { x: (pageH - py) * scale, y: px * scale };
    case 180: return { x: (pageW - px) * scale, y: (pageH - py) * scale };
    case 270: return { x: py * scale, y: (pageW - px) * scale };
    default:  return { x: px * scale, y: py * scale };
  }
}

function bboxToCanvasRect(
  bbox: [number, number, number, number],
  pageW: number,
  pageH: number,
  rotation: number,
  scale: number,
): { left: number; top: number; width: number; height: number } {
  const [x0, y0, x1, y1] = bbox;
  const corners = [
    toCanvas(x0, y0, pageW, pageH, rotation, scale),
    toCanvas(x1, y0, pageW, pageH, rotation, scale),
    toCanvas(x0, y1, pageW, pageH, rotation, scale),
    toCanvas(x1, y1, pageW, pageH, rotation, scale),
  ];
  const xs = corners.map((c) => c.x);
  const ys = corners.map((c) => c.y);
  const left = Math.min(...xs);
  const top  = Math.min(...ys);
  return { left, top, width: Math.max(...xs) - left, height: Math.max(...ys) - top };
}

export default function TextEditPreviewLayer({
  previews,
  scale,
  pageWidth,
  pageHeight,
  userRotation,
}: Props) {
  if (previews.length === 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {previews.map((p) => {
        const cover = bboxToCanvasRect(p.coverRect, pageWidth, pageHeight, userRotation, scale);
        const ins = toCanvas(p.insertX, p.insertY, pageWidth, pageHeight, userRotation, scale);
        const fontSizePx = p.fontSize * scale;
        const text = p.runs.map((r) => r.text).join("");
        const color = p.runs[0]?.color ?? "#000000";

        return (
          <div key={p.key}>
            {/* Opaque cover matching backend redaction rect */}
            <div
              style={{
                position: "absolute",
                left: cover.left,
                top: cover.top,
                width: cover.width,
                height: cover.height,
                backgroundColor: p.backgroundColor,
              }}
            />
            {/* Preview text at same origin the backend will use */}
            <span
              style={{
                position: "absolute",
                left: ins.x,
                top: ins.y,
                fontSize: fontSizePx,
                lineHeight: 1.2,
                color,
                fontFamily: "Helvetica, Arial, sans-serif",
                whiteSpace: "pre",
                userSelect: "none",
              }}
            >
              {text}
            </span>
          </div>
        );
      })}
    </div>
  );
}
