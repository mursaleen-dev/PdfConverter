"use client";

import { useEffect, useRef } from "react";
import { Trash2, Copy, ArrowUp, ArrowDown } from "lucide-react";

interface ActionCallbacks {
  onDelete: () => void;
  onDuplicate: () => void;
  onBringForward: () => void;
  onSendBackward: () => void;
}

// ── Floating toolbar anchored above selected object(s) ────────────────────────

interface SelectionToolbarProps extends ActionCallbacks {
  /** Canvas-space bounding rect of the selection. */
  bounds: { left: number; top: number; width: number; height: number };
  /** Keep toolbar within this width (canvas width in px). */
  canvasWidth: number;
}

const TOOLBAR_HEIGHT = 32;
const TOOLBAR_WIDTH = 136; // 4 buttons × 34px
const TOOLBAR_GAP = 6;

export function SelectionToolbar({
  bounds,
  canvasWidth,
  onDelete,
  onDuplicate,
  onBringForward,
  onSendBackward,
}: SelectionToolbarProps) {
  // Clamp so toolbar stays within canvas width
  const rawLeft = bounds.left + bounds.width / 2 - TOOLBAR_WIDTH / 2;
  const left = Math.max(0, Math.min(rawLeft, canvasWidth - TOOLBAR_WIDTH));
  const top = Math.max(0, bounds.top - TOOLBAR_HEIGHT - TOOLBAR_GAP);

  return (
    <div
      className="absolute z-30 flex items-center gap-0.5 rounded-lg border border-neutral-200 bg-white px-1 py-1 shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
      style={{ left, top, height: TOOLBAR_HEIGHT }}
      // Stop propagation so Fabric doesn't get confused by clicks on the toolbar
      onMouseDown={(e) => e.stopPropagation()}
    >
      <ToolbarBtn title="Delete (Del)" onClick={onDelete} danger>
        <Trash2 className="h-3.5 w-3.5" />
      </ToolbarBtn>
      <ToolbarBtn title="Duplicate" onClick={onDuplicate}>
        <Copy className="h-3.5 w-3.5" />
      </ToolbarBtn>
      <ToolbarBtn title="Bring forward" onClick={onBringForward}>
        <ArrowUp className="h-3.5 w-3.5" />
      </ToolbarBtn>
      <ToolbarBtn title="Send backward" onClick={onSendBackward}>
        <ArrowDown className="h-3.5 w-3.5" />
      </ToolbarBtn>
    </div>
  );
}

function ToolbarBtn({
  children,
  title,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={[
        "flex h-6 w-6 items-center justify-center rounded",
        danger
          ? "text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
          : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

// ── Right-click context menu ──────────────────────────────────────────────────

interface ContextMenuProps extends ActionCallbacks {
  screenX: number;
  screenY: number;
  onClose: () => void;
}

export function ContextMenu({
  screenX,
  screenY,
  onClose,
  onDelete,
  onDuplicate,
  onBringForward,
  onSendBackward,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handle, { capture: true });
    return () => document.removeEventListener("mousedown", handle, { capture: true });
  }, [onClose]);

  // Clamp to viewport
  const style: React.CSSProperties = {
    position: "fixed",
    top: screenY,
    left: screenX,
    zIndex: 9999,
  };

  const item = (label: string, action: () => void, isDelete = false) => (
    <button
      key={label}
      onClick={() => { action(); onClose(); }}
      className={[
        "flex w-full items-center px-3 py-1.5 text-left text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800",
        isDelete ? "text-red-500 dark:text-red-400" : "text-neutral-700 dark:text-neutral-200",
      ].join(" ")}
    >
      {label}
    </button>
  );

  return (
    <div
      ref={menuRef}
      style={style}
      className="min-w-[140px] rounded-lg border border-neutral-200 bg-white py-1 shadow-xl dark:border-neutral-700 dark:bg-neutral-900"
    >
      {item("Bring to front", onBringForward)}
      {item("Send to back", onSendBackward)}
      <div className="my-1 border-t border-neutral-100 dark:border-neutral-800" />
      {item("Duplicate", onDuplicate)}
      {item("Delete", onDelete, true)}
    </div>
  );
}
