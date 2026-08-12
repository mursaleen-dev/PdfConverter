"use client";

import { useCallback, useEffect, useRef } from "react";
import { X, Check } from "lucide-react";
import type {
  ExtractedParagraph,
  ExtractedSpan,
  TextRun,
} from "./types";

interface InlineEditorProps {
  para: ExtractedParagraph;
  singleSpan: ExtractedSpan | null;  // non-null for Alt-click (single-span mode)
  rect: { left: number; top: number; width: number; height: number };
  domSize: number;    // dominant font size in pts × scale → px for CSS
  scale: number;
  onCommit: (runs: TextRun[]) => void;
  onCancel: () => void;
}

// ── DOM → TextRun[] ───────────────────────────────────────────────────────────

function rgbStringToHex(rgb: string): string {
  const m = /rgb\((\d+),\s*(\d+),\s*(\d+)\)/.exec(rgb);
  if (!m) return "#000000";
  const r = parseInt(m[1]).toString(16).padStart(2, "0");
  const g = parseInt(m[2]).toString(16).padStart(2, "0");
  const b = parseInt(m[3]).toString(16).padStart(2, "0");
  return `#${r}${g}${b}`;
}

function domToRuns(el: HTMLElement): TextRun[] {
  const runs: TextRun[] = [];
  let currentBold = false;
  let currentItalic = false;
  let currentColor = "#000000";

  function walk(node: Node): void {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent ?? "";
      if (text) {
        runs.push({ text, bold: currentBold, italic: currentItalic, sizeScale: 1.0, color: currentColor });
      }
      return;
    }
    if (!(node instanceof HTMLElement)) return;

    const savedBold = currentBold;
    const savedItalic = currentItalic;
    const savedColor = currentColor;

    const tag = node.tagName.toLowerCase();
    if (tag === "b" || tag === "strong") currentBold = true;
    if (tag === "i" || tag === "em") currentItalic = true;

    const style = node.style;
    if (style.fontWeight === "bold" || Number(style.fontWeight) >= 700) currentBold = true;
    if (style.fontStyle === "italic" || style.fontStyle === "oblique") currentItalic = true;
    if (style.color) currentColor = rgbStringToHex(window.getComputedStyle(node).color);

    // Line breaks become space characters
    if (tag === "br") {
      runs.push({ text: "\n", bold: currentBold, italic: currentItalic, sizeScale: 1.0, color: currentColor });
    } else {
      for (const child of node.childNodes) walk(child);
    }

    currentBold = savedBold;
    currentItalic = savedItalic;
    currentColor = savedColor;
  }

  walk(el);

  // Merge adjacent runs with identical style
  const merged: TextRun[] = [];
  for (const run of runs) {
    const prev = merged[merged.length - 1];
    if (
      prev &&
      prev.bold === run.bold &&
      prev.italic === run.italic &&
      prev.color === run.color &&
      prev.sizeScale === run.sizeScale
    ) {
      merged[merged.length - 1] = { ...prev, text: prev.text + run.text };
    } else {
      merged.push({ ...run });
    }
  }
  return merged.filter((r) => r.text);
}

// ── Pre-fill HTML ─────────────────────────────────────────────────────────────

function buildInitialHTML(para: ExtractedParagraph, singleSpan: ExtractedSpan | null): string {
  const renderSpan = (s: ExtractedSpan, textValue = s.text) => {
      const text = textValue.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const fw = s.bold ? "bold" : "normal";
      const fs = s.italic ? "italic" : "normal";
      return `<span style="font-weight:${fw};font-style:${fs};color:${s.color}">${text}</span>`;
  };

  if (singleSpan) return renderSpan(singleSpan);

  return para.lines
    .map((line) => {
      const spans = line.spans.filter((s) => s.isLtr);
      return spans.map((span, index) => {
        if (index === 0) return renderSpan(span);
        const previous = spans[index - 1];
        const gap = span.bbox[0] - previous.bbox[2];
        const needsSpace =
          gap > Math.max(0.5, Math.min(span.size, previous.size) * 0.08) &&
          !previous.text.endsWith(" ") &&
          !span.text.startsWith(" ");
        return renderSpan(span, `${needsSpace ? " " : ""}${span.text}`);
      }).join("");
    })
    .join("<br>");
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function InlineEditor({
  para,
  singleSpan,
  rect,
  domSize,
  scale,
  onCommit,
  onCancel,
}: InlineEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);

  // Initialise content and move cursor to end
  useEffect(() => {
    if (!editorRef.current) return;
    editorRef.current.innerHTML = buildInitialHTML(para, singleSpan);
    const range = document.createRange();
    range.selectNodeContents(editorRef.current);
    range.collapse(false);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    editorRef.current.focus();
  }, [para, singleSpan]);

  const commit = useCallback(() => {
    if (!editorRef.current) return;
    const rawRuns = domToRuns(editorRef.current);
    if (rawRuns.length === 0 || rawRuns.every((r) => !r.text.trim())) {
      onCancel();
      return;
    }
    onCommit(rawRuns);
  }, [onCommit, onCancel]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      commit();
      return;
    }
  };

  const displaySize = Math.max(10, domSize * scale);  // CSS px

  // Keep toolbar above the text area; clamp so it never goes above the canvas top
  const safeTop = Math.max(4, rect.top - 36);

  return (
    <div
      className="absolute z-30 shadow-xl"
      style={{ left: rect.left, top: safeTop, width: Math.max(rect.width, 200) }}
    >
      {/* Minimal toolbar: confirm / cancel */}
      <div className="flex items-center gap-1 rounded-t-lg border border-neutral-200 bg-white px-2 py-1 box-border dark:border-neutral-700 dark:bg-neutral-900">
        <div className="flex-1" />
        <button
          onMouseDown={(e) => { e.preventDefault(); commit(); }}
          className="rounded p-1 text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/20"
          title="Commit (Enter)"
        >
          <Check className="h-3.5 w-3.5" />
        </button>
        <button
          onMouseDown={(e) => { e.preventDefault(); onCancel(); }}
          className="rounded p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          title="Cancel (Esc)"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Editable area */}
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        onKeyDown={handleKeyDown}
        className="min-h-[1.5em] w-full overflow-hidden rounded-b-lg border border-t-0 border-neutral-200 bg-white/95 px-1 py-0.5 outline-none focus:border-blue-400 dark:border-neutral-700 dark:bg-neutral-900/95"
        style={{
          fontSize: displaySize,
          lineHeight: 1.2,
          minWidth: rect.width,
          minHeight: rect.height,
          caretColor: "currentColor",
        }}
        spellCheck={false}
      />
    </div>
  );
}
