"use client";

import { useRef } from "react";
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
  verticalListSortingStrategy,
  useSortable,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, ChevronLeft, ChevronRight } from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageDescriptor } from "./types";
import ThumbnailItem from "./ThumbnailItem";
import type { EditorState } from "./useEditorState";

interface SortableThumbnailProps {
  descriptor: PageDescriptor;
  index: number;
  pdfDoc: PDFDocumentProxy | null;
  thumbCache: React.MutableRefObject<Map<string, string>>;
  isSelected: boolean;
  isEditing: boolean;
  onNavigate: (id: string) => void;
  onSelect: (id: string, e: React.MouseEvent) => void;
}

function SortableThumbnail(props: SortableThumbnailProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.descriptor.pageId });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 50 : undefined,
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

interface PageSidebarProps {
  pages: PageDescriptor[];
  pdfDoc: PDFDocumentProxy | null;
  thumbCache: React.MutableRefObject<Map<string, string>>;
  editorState: EditorState;
  collapsed: boolean;
  onCollapsedChange: (v: boolean) => void;
}

export default function PageSidebar({
  pages,
  pdfDoc,
  thumbCache,
  editorState,
  collapsed,
  onCollapsedChange,
}: PageSidebarProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    editorState.reorderPagesCmd(String(active.id), String(over.id));
  };

  const handleNavigate = (pageId: string) => {
    editorState.navigateTo(pageId);
  };

  const handleSelect = (pageId: string, e: React.MouseEvent) => {
    if (e.shiftKey) {
      editorState.rangeSelect(pageId);
    } else {
      editorState.toggleSelect(pageId);
    }
  };

  if (collapsed) {
    return (
      <div className="flex flex-col items-center border-r border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 pt-2">
        <button
          onClick={() => onCollapsedChange(false)}
          aria-label="Expand page panel"
          className="rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-[118px] shrink-0 flex-col border-r border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-100 px-2 py-1.5 dark:border-neutral-800">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
          Pages
        </span>
        <button
          onClick={() => onCollapsedChange(true)}
          aria-label="Collapse page panel"
          className="rounded p-0.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Scrollable thumbnail list */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden py-2 px-1 space-y-1">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={pages.map((p) => p.pageId)}
            strategy={verticalListSortingStrategy}
          >
            {pages.map((desc, i) => (
              <SortableThumbnail
                key={desc.pageId}
                descriptor={desc}
                index={i}
                pdfDoc={pdfDoc}
                thumbCache={thumbCache}
                isSelected={editorState.selectedPageIds.has(desc.pageId)}
                isEditing={editorState.currentEditingPageId === desc.pageId}
                onNavigate={handleNavigate}
                onSelect={handleSelect}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}
