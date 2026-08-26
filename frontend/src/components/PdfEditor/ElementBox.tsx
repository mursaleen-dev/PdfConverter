"use client";

import { useRef, useState } from "react";
import { Rnd } from "react-rnd";
import { X } from "lucide-react";
import type { EditorElement, FontFamily } from "./types";

const COLORS = ["#111111", "#dc2626", "#2563eb", "#16a34a", "#d97706"];

const FONT_FAMILIES: { value: FontFamily; label: string; css: string }[] = [
  { value: "helvetica", label: "Sans", css: "Arial, Helvetica, sans-serif" },
  { value: "times",     label: "Serif", css: "'Times New Roman', Times, serif" },
  { value: "courier",   label: "Mono", css: "'Courier New', Courier, monospace" },
];

interface ElementBoxProps {
  element: EditorElement;
  selected: boolean;
  onSelect: () => void;
  onChange: (patch: Partial<EditorElement>) => void;
  onDelete: () => void;
}

export default function ElementBox({ element, selected, onSelect, onChange, onDelete }: ElementBoxProps) {
  const [editing, setEditing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const cssFontFamily =
    FONT_FAMILIES.find((f) => f.value === element.fontFamily)?.css ??
    FONT_FAMILIES[0].css;

  const textStyle: React.CSSProperties = {
    fontSize: element.fontSize,
    color: element.color,
    fontFamily: cssFontFamily,
    fontWeight: element.bold ? "bold" : "normal",
    fontStyle: element.italic ? "italic" : "normal",
    textDecoration: element.underline ? "underline" : "none",
  };

  return (
    <Rnd
      bounds="parent"
      position={{ x: element.x, y: element.y }}
      size={{ width: element.width, height: element.height }}
      onDragStart={onSelect}
      onDragStop={(_e, d) => onChange({ x: d.x, y: d.y })}
      onResizeStart={onSelect}
      onResizeStop={(_e, _dir, ref, _delta, pos) =>
        onChange({
          width: parseFloat(ref.style.width),
          height: parseFloat(ref.style.height),
          x: pos.x,
          y: pos.y,
        })
      }
      onMouseDown={onSelect}
      className={`group ${selected ? "z-20" : "z-10"}`}
    >
      <div
        className={`relative h-full w-full ${
          selected
            ? "outline outline-2 outline-blue-500"
            : "outline outline-1 outline-dashed outline-neutral-300"
        }`}
      >
        {selected && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="absolute -right-2.5 -top-2.5 z-30 flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-white shadow"
            aria-label="Delete element"
          >
            <X className="h-3 w-3" />
          </button>
        )}

        {element.type === "text" &&
          (editing ? (
            <textarea
              ref={textareaRef}
              autoFocus
              defaultValue={element.text}
              onBlur={(e) => {
                onChange({ text: e.target.value });
                setEditing(false);
              }}
              style={textStyle}
              className="h-full w-full resize-none bg-white/90 p-1 outline-none"
            />
          ) : (
            <div
              onDoubleClick={() => setEditing(true)}
              style={textStyle}
              className="h-full w-full overflow-hidden whitespace-pre-wrap break-words bg-transparent p-1 leading-tight"
            >
              {element.text || "Double-click to edit"}
            </div>
          ))}

        {element.type === "image" && element.imageDataUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={element.imageDataUrl}
            alt="Stamp"
            draggable={false}
            className="h-full w-full select-none object-contain"
          />
        )}

        {/* Toolbar — visible only when a text element is selected */}
        {selected && element.type === "text" && (
          <div className="absolute -top-10 left-0 flex items-center gap-1 rounded-md border border-neutral-200 bg-white px-1.5 py-1 shadow-sm dark:border-neutral-700 dark:bg-neutral-900">
            {/* Font family */}
            {FONT_FAMILIES.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onChange({ fontFamily: f.value });
                }}
                style={{ fontFamily: f.css }}
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                  (element.fontFamily ?? "helvetica") === f.value
                    ? "bg-neutral-200 dark:bg-neutral-700"
                    : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
                }`}
                title={f.label}
              >
                {f.label}
              </button>
            ))}

            <span className="mx-0.5 h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

            {/* Bold */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ bold: !element.bold });
              }}
              className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                element.bold
                  ? "bg-neutral-200 dark:bg-neutral-700"
                  : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
              }`}
              title="Bold"
            >
              B
            </button>

            {/* Italic */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ italic: !element.italic });
              }}
              className={`rounded px-1.5 py-0.5 text-xs italic ${
                element.italic
                  ? "bg-neutral-200 dark:bg-neutral-700"
                  : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
              }`}
              title="Italic"
            >
              I
            </button>

            {/* Underline */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ underline: !element.underline });
              }}
              className={`rounded px-1.5 py-0.5 text-xs underline ${
                element.underline
                  ? "bg-neutral-200 dark:bg-neutral-700"
                  : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
              }`}
              title="Underline"
            >
              U
            </button>

            <span className="mx-0.5 h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

            {/* Color swatches */}
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onChange({ color: c });
                }}
                style={{ backgroundColor: c }}
                className={`h-4 w-4 rounded-full ${
                  element.color === c ? "ring-2 ring-offset-1 ring-neutral-400" : ""
                }`}
                aria-label={`Color ${c}`}
              />
            ))}

            <span className="mx-0.5 h-4 w-px bg-neutral-200 dark:bg-neutral-700" />

            {/* Font size */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ fontSize: Math.max(8, (element.fontSize ?? 16) - 2) });
              }}
              className="px-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
              title="Decrease font size"
            >
              A-
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ fontSize: Math.min(134, (element.fontSize ?? 16) + 2) });
              }}
              className="px-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
              title="Increase font size"
            >
              A+
            </button>
          </div>
        )}
      </div>
    </Rnd>
  );
}
