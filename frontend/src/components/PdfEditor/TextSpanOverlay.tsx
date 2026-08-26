"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PdfTextSpan } from "./types";

export const HIT_PADDING = 16; // px on each side — exported so callers can read it

interface TextSpanOverlayProps {
  span: PdfTextSpan;
  editedText: string | undefined;
  onEdit: (newText: string) => void;
}

/**
 * Invisible overlay positioned over a detected PDF text run.
 *
 * Click handling is self-contained: the outer div's onPointerDown activates
 * the span directly.  Hover state is tracked in React so the blue highlight
 * is not overridden by the higher-specificity inline style prop.
 */
export default function TextSpanOverlay({ span, editedText, onEdit }: TextSpanOverlayProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [hovered, setHovered] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isEdited = editedText !== undefined && editedText !== span.text;
  const displayText = editedText ?? span.text;

  useEffect(() => {
    if (editing) textareaRef.current?.select();
  }, [editing]);

  const commit = useCallback(() => {
    setEditing(false);
    if (draft !== displayText) onEdit(draft);
  }, [draft, displayText, onEdit]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
    if (e.key === "Escape") setEditing(false);
  };

  const outerStyle: React.CSSProperties = {
    position:    "absolute",
    left:        span.canvasX - HIT_PADDING,
    top:         span.canvasY - HIT_PADDING,
    width:       span.canvasWidth  + 2 * HIT_PADDING,
    height:      span.canvasHeight + 2 * HIT_PADDING,
    boxSizing:   "border-box",
    touchAction: "manipulation",
    userSelect:  "none",
  };

  const innerStyle: React.CSSProperties = {
    position:     "absolute",
    top:          HIT_PADDING,
    right:        HIT_PADDING,
    bottom:       HIT_PADDING,
    left:         HIT_PADDING,
    boxSizing:    "border-box",
    borderRadius: 2,
  };

  if (span.isRotated) {
    return (
      <div style={{ ...outerStyle, cursor: "not-allowed", zIndex: 20 }}
           title="Rotated text cannot be edited in-place">
        <div style={{ ...innerStyle, border: "1px dashed rgba(156,163,175,0.5)" }} />
      </div>
    );
  }

  const editMinWidth  = Math.max(span.canvasWidth  + 2 * HIT_PADDING, 220);
  const editMinHeight = Math.max(span.canvasHeight + 2 * HIT_PADDING, 64);

  if (editing) {
    return (
      <div style={{ ...outerStyle, width: editMinWidth, height: editMinHeight, zIndex: 30 }}>
        <textarea
          ref={textareaRef}
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          style={{
            position:   "absolute",
            inset:      0,
            fontSize:   Math.max(span.fontSizePx, 14),
            lineHeight: 1.4,
            background: "rgba(255,255,255,0.97)",
            border:     "2px solid #3b82f6",
            borderRadius: 3,
            outline:    "none",
            resize:     "both",
            padding:    "4px 8px",
            fontFamily: "inherit",
            color:      "#111",
            boxSizing:  "border-box",
            boxShadow:  "0 2px 8px rgba(0,0,0,0.18)",
          }}
        />
      </div>
    );
  }

  const borderColor = isEdited ? "#22c55e" : hovered ? "#60a5fa" : "transparent";
  const bgColor     = isEdited ? "rgba(34,197,94,0.07)" : hovered ? "rgba(59,130,246,0.1)" : "transparent";

  return (
    <div
      style={{ ...outerStyle, cursor: "text", zIndex: 20 }}
      title={span.text}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onPointerDown={(e) => {
        e.stopPropagation();
        setDraft(displayText);
        setEditing(true);
      }}
    >
      <div
        style={{
          ...innerStyle,
          border:     `1px solid ${borderColor}`,
          background: bgColor,
          transition: "background 80ms, border-color 80ms",
        }}
      />
    </div>
  );
}
