"use client";

import {
  MousePointer2,
  Type,
  ImagePlus,
  PenLine,
  Square,
  Circle,
  Pencil,
  Highlighter,
  Strikethrough,
  Eraser,
  Minus,
  PencilLine,
} from "lucide-react";
import type { ActiveTool, ToolSettings } from "./types";

interface ToolbarProps {
  activeTool: ActiveTool;
  onToolChange: (tool: ActiveTool) => void;
  toolSettings: ToolSettings;
  onSettingsChange: (patch: Partial<ToolSettings>) => void;
  onAddImage: () => void;
  onAddSignature: () => void;
}

interface ToolBtn {
  id: ActiveTool;
  icon: React.ReactNode;
  label: string;
  action?: () => void;
}

export default function Toolbar({
  activeTool,
  onToolChange,
  toolSettings,
  onSettingsChange,
  onAddImage,
  onAddSignature,
}: ToolbarProps) {
  const groups: ToolBtn[][] = [
    [{ id: "select", icon: <MousePointer2 className="h-4 w-4" />, label: "Select" }],
    [{ id: "edit-text", icon: <PencilLine className="h-4 w-4" />, label: "Edit Text" }],
    [
      { id: "text", icon: <Type className="h-4 w-4" />, label: "Text" },
      {
        id: "image",
        icon: <ImagePlus className="h-4 w-4" />,
        label: "Image",
        action: onAddImage,
      },
      {
        id: "signature",
        icon: <PenLine className="h-4 w-4" />,
        label: "Signature",
        action: onAddSignature,
      },
    ],
    [
      { id: "rect", icon: <Square className="h-4 w-4" />, label: "Rectangle" },
      { id: "ellipse", icon: <Circle className="h-4 w-4" />, label: "Ellipse" },
      { id: "freehand", icon: <Pencil className="h-4 w-4" />, label: "Draw" },
    ],
    [
      { id: "highlight", icon: <Highlighter className="h-4 w-4" />, label: "Highlight" },
      { id: "strikethrough", icon: <Strikethrough className="h-4 w-4" />, label: "Strikethrough" },
      { id: "whiteout", icon: <Minus className="h-4 w-4" />, label: "Whiteout" },
    ],
    [{ id: "eraser", icon: <Eraser className="h-4 w-4" />, label: "Eraser" }],
  ];

  const btn = (t: ToolBtn) => {
    const active = activeTool === t.id;
    return (
      <button
        key={t.id}
        title={t.label}
        onClick={() => {
          if (t.action) t.action();
          else onToolChange(t.id);
        }}
        className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
          active
            ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
            : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
        }`}
      >
        {t.icon}
        <span className="hidden sm:inline">{t.label}</span>
      </button>
    );
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-200 bg-white px-4 py-2 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
      {/* Tool groups */}
      <div className="flex flex-wrap items-center gap-1">
        {groups.map((group, gi) => (
          <div key={gi} className="flex items-center gap-0.5">
            {group.map(btn)}
            {gi < groups.length - 1 && (
              <div className="mx-1.5 h-5 w-px bg-neutral-200 dark:bg-neutral-700" />
            )}
          </div>
        ))}
      </div>

      {/* Inline settings — shown for relevant active tools */}
      <div className="ml-auto flex flex-wrap items-center gap-3">
        {/* Text settings */}
        {activeTool === "text" && (
          <>
            <select
              value={toolSettings.fontFamily}
              onChange={(e) => onSettingsChange({ fontFamily: e.target.value })}
              className="rounded border border-neutral-200 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value="Helvetica">Helvetica</option>
              <option value="Times-Roman">Times</option>
              <option value="Courier">Courier</option>
            </select>
            <div className="flex items-center gap-1">
              <button
                onClick={() => onSettingsChange({ fontSize: Math.max(6, toolSettings.fontSize - 2) })}
                className="rounded border border-neutral-200 px-1.5 py-0.5 text-xs dark:border-neutral-700"
              >
                A−
              </button>
              <span className="w-8 text-center text-xs">{toolSettings.fontSize}</span>
              <button
                onClick={() => onSettingsChange({ fontSize: Math.min(72, toolSettings.fontSize + 2) })}
                className="rounded border border-neutral-200 px-1.5 py-0.5 text-xs dark:border-neutral-700"
              >
                A+
              </button>
            </div>
            <div className="flex items-center gap-1">
              <button
                title="Bold"
                onClick={() => onSettingsChange({ bold: !toolSettings.bold })}
                className={`rounded px-1.5 py-0.5 text-xs font-bold ${toolSettings.bold ? "bg-neutral-200 dark:bg-neutral-700" : ""}`}
              >
                B
              </button>
              <button
                title="Italic"
                onClick={() => onSettingsChange({ italic: !toolSettings.italic })}
                className={`rounded px-1.5 py-0.5 text-xs italic ${toolSettings.italic ? "bg-neutral-200 dark:bg-neutral-700" : ""}`}
              >
                I
              </button>
              <button
                title="Underline"
                onClick={() => onSettingsChange({ underline: !toolSettings.underline })}
                className={`rounded px-1.5 py-0.5 text-xs underline ${toolSettings.underline ? "bg-neutral-200 dark:bg-neutral-700" : ""}`}
              >
                U
              </button>
            </div>
            <ColorSwatch
              value={toolSettings.textColor}
              onChange={(c) => onSettingsChange({ textColor: c })}
              label="Text color"
            />
          </>
        )}

        {/* Shape settings */}
        {(activeTool === "rect" || activeTool === "ellipse") && (
          <>
            <label className="flex items-center gap-1 text-xs text-neutral-500">
              Fill
              <ColorSwatch
                value={toolSettings.fillColor === "transparent" ? "#ffffff" : toolSettings.fillColor}
                onChange={(c) => onSettingsChange({ fillColor: c })}
                label="Fill color"
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-neutral-500">
              Stroke
              <ColorSwatch
                value={toolSettings.strokeColor}
                onChange={(c) => onSettingsChange({ strokeColor: c })}
                label="Stroke color"
              />
            </label>
            <div className="flex items-center gap-1">
              <span className="text-xs text-neutral-500">Width</span>
              <input
                type="range"
                min={0.5}
                max={12}
                step={0.5}
                value={toolSettings.strokeWidth}
                onChange={(e) => onSettingsChange({ strokeWidth: parseFloat(e.target.value) })}
                className="w-20"
              />
              <span className="w-6 text-xs text-neutral-500">{toolSettings.strokeWidth}</span>
            </div>
          </>
        )}

        {/* Freehand settings */}
        {activeTool === "freehand" && (
          <>
            <ColorSwatch
              value={toolSettings.freehandColor}
              onChange={(c) => onSettingsChange({ freehandColor: c })}
              label="Pen color"
            />
            <div className="flex items-center gap-1">
              <span className="text-xs text-neutral-500">Width</span>
              <input
                type="range"
                min={1}
                max={20}
                step={1}
                value={toolSettings.freehandWidth}
                onChange={(e) => onSettingsChange({ freehandWidth: parseInt(e.target.value) })}
                className="w-20"
              />
              <span className="w-6 text-xs text-neutral-500">{toolSettings.freehandWidth}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ColorSwatch({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (c: string) => void;
  label: string;
}) {
  return (
    <label className="cursor-pointer" title={label}>
      <span
        className="inline-block h-5 w-5 rounded border border-neutral-300 dark:border-neutral-600"
        style={{ background: value }}
      />
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="sr-only"
      />
    </label>
  );
}
