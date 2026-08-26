"use client";

import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  RotateCw,
  RotateCcw,
  Trash2,
  Copy,
  PlusSquare,
  GripVertical,
  X,
} from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageDescriptor } from "./types";
import ThumbnailItem from "./ThumbnailItem";
import type { EditorState } from "./useEditorState";

interface SortableGridThumbnailProps {
  descriptor: PageDescriptor;
  index: number;
  pdfDoc: PDFDocumentProxy | null;
  thumbCache: React.MutableRefObject<Map<string, string>>;
  isSelected: boolean;
  isEditing: boolean;
  onNavigate: (id: string) => void;
  onSelect: (id: string, e: React.MouseEvent) => void;
}

function SortableGridThumbnail(props: SortableGridThumbnailProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.descriptor.pageId });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <ThumbnailItem
        {...props}
        dragHandle={
          <button
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing rounded p-0.5 text-neutral-400 hover:text-neutral-600"
            aria-label="Drag to reorder"
            onClick={(e) => e.stopPropagation()}
          >
            <GripVertical className="h-3.5 w-3.5" />
          </button>
        }
      />
    </div>
  );
}

interface OrganizeGridProps {
  pages: PageDescriptor[];
  pdfDoc: PDFDocumentProxy | null;
  thumbCache: React.MutableRefObject<Map<string, string>>;
  editorState: EditorState;
  scale: number;
  onClose: () => void;
}

export default function OrganizeGrid({
  pages,
  pdfDoc,
  thumbCache,
  editorState,
  scale,
  onClose,
}: OrganizeGridProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    editorState.reorderPagesCmd(String(active.id), String(over.id));
  };

  const selected = editorState.selectedPageIds;
  const selectedIds = [...selected];
  const hasSelection = selectedIds.length > 0;

  const handleNavigate = (pageId: string) => {
    editorState.navigateTo(pageId);
    onClose();
  };

  const handleSelect = (pageId: string, e: React.MouseEvent) => {
    if (e.shiftKey) {
      editorState.rangeSelect(pageId);
    } else {
      editorState.toggleSelect(pageId);
    }
  };

  return (
    <div className="flex h-full flex-col bg-neutral-50 dark:bg-neutral-900">
      {/* Organize mode toolbar */}
      <div className="flex items-center gap-2 border-b border-neutral-200 bg-white px-4 py-2 dark:border-neutral-800 dark:bg-neutral-950">
        <span className="mr-auto text-sm font-semibold">Organize Pages</span>

        {hasSelection && (
          <>
            <span className="text-xs text-neutral-500">{selectedIds.length} selected</span>
            <ToolBtn
              icon={<RotateCcw className="h-4 w-4" />}
              label="Rotate CCW"
              onClick={() => editorState.rotatePagesCmd(selectedIds, "ccw", scale)}
            />
            <ToolBtn
              icon={<RotateCw className="h-4 w-4" />}
              label="Rotate CW"
              onClick={() => editorState.rotatePagesCmd(selectedIds, "cw", scale)}
            />
            <ToolBtn
              icon={<Copy className="h-4 w-4" />}
              label="Duplicate"
              onClick={() => editorState.duplicatePagesCmd(selectedIds)}
            />
            <ToolBtn
              icon={<Trash2 className="h-4 w-4" />}
              label="Delete"
              danger
              onClick={() => {
                if (pages.length - selectedIds.length < 1) return;
                editorState.deletePagesCmd(selectedIds);
              }}
            />
          </>
        )}

        {pages.length > 0 && (
          <ToolBtn
            icon={<PlusSquare className="h-4 w-4" />}
            label="Add blank page"
            onClick={() => {
              const lastSelected = selectedIds[selectedIds.length - 1] ?? pages[pages.length - 1].pageId;
              editorState.insertBlankCmd(lastSelected);
            }}
          />
        )}

        <div className="mx-2 h-5 w-px bg-neutral-200 dark:bg-neutral-700" />

        <button
          onClick={onClose}
          className="flex items-center gap-1.5 rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
        >
          <X className="h-3.5 w-3.5" />
          Done
        </button>
      </div>

      {/* Select all / none */}
      <div className="flex items-center gap-3 px-4 py-1.5 text-xs text-neutral-500">
        <button className="hover:text-neutral-800 dark:hover:text-neutral-200" onClick={editorState.selectAll}>
          Select all
        </button>
        {hasSelection && (
          <button className="hover:text-neutral-800 dark:hover:text-neutral-200" onClick={editorState.clearSelection}>
            Deselect all
          </button>
        )}
        <span className="ml-auto">{pages.length} pages</span>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-4">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={pages.map((p) => p.pageId)}
            strategy={rectSortingStrategy}
          >
            <div className="flex flex-wrap gap-4">
              {pages.map((desc, i) => (
                <SortableGridThumbnail
                  key={desc.pageId}
                  descriptor={desc}
                  index={i}
                  pdfDoc={pdfDoc}
                  thumbCache={thumbCache}
                  isSelected={selected.has(desc.pageId)}
                  isEditing={editorState.currentEditingPageId === desc.pageId}
                  onNavigate={handleNavigate}
                  onSelect={handleSelect}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}

interface ToolBtnProps {
  icon: React.ReactNode;
  label: string;
  danger?: boolean;
  onClick: () => void;
}

function ToolBtn({ icon, label, danger, onClick }: ToolBtnProps) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={[
        "flex items-center gap-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition-colors",
        danger
          ? "border-red-200 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/30"
          : "border-neutral-200 text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800",
      ].join(" ")}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
