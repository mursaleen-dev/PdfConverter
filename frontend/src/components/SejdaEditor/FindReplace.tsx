"use client";

import { useCallback, useRef, useState } from "react";
import { Search, X, Replace, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import type { ExtractedPage, PageDescriptor, SearchMatch, TextEditEntry, TextRun } from "./types";
import { searchText } from "@/lib/api";

interface FindReplaceProps {
  file: File;
  pages: PageDescriptor[];
  extractAll: (pages: Array<{ pageId: string; sourceIndex: number }>) => Promise<Map<string, ExtractedPage>>;
  onApplyReplacements: (entries: TextEditEntry[]) => void;
  onClose: () => void;
}

interface MatchWithSelection extends SearchMatch {
  id: string;
  selected: boolean;
}

export default function FindReplace({
  file,
  pages,
  extractAll,
  onApplyReplacements,
  onClose,
}: FindReplaceProps) {
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [matches, setMatches] = useState<MatchWithSelection[]>([]);
  const [localExtractions, setLocalExtractions] = useState<Map<string, ExtractedPage>>(new Map());
  const [searching, setSearching] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(true);
  const queryRef = useRef<HTMLInputElement>(null);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      const pageScope = pages
        .filter((p) => !p.isBlank && p.sourceIndex >= 0)
        .map((p) => ({ sourceIndex: p.sourceIndex, pageId: p.pageId }));

      // Run text search and page extraction in parallel so Replace works on all pages
      const [raw, extracted] = await Promise.all([
        searchText(file, query.trim(), pageScope),
        extractAll(pageScope),
      ]);

      setLocalExtractions(extracted);
      const withSel: MatchWithSelection[] = raw.map((m, i) => ({
        ...m,
        id: `match-${i}`,
        selected: true,
      }));
      setMatches(withSel);
    } catch {
      setError("Search failed. Check that the file is accessible.");
    } finally {
      setSearching(false);
    }
  }, [file, pages, query, extractAll]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
    if (e.key === "Escape") onClose();
  };

  const toggleMatch = (id: string) => {
    setMatches((prev) =>
      prev.map((m) => (m.id === id ? { ...m, selected: !m.selected } : m))
    );
  };

  const toggleAll = (sel: boolean) => {
    setMatches((prev) => prev.map((m) => ({ ...m, selected: sel })));
  };

  const handleApply = useCallback(async () => {
    const selected = matches.filter((m) => m.selected);
    if (!selected.length || !replacement) return;

    setApplying(true);
    setError("");
    try {
      const entries: TextEditEntry[] = [];

      for (const match of selected) {
        const extractedPage = localExtractions.get(match.pageId);
        if (!extractedPage) continue;

        // Find paragraph whose bbox contains the match bbox
        const para = extractedPage.paragraphs.find((p) =>
          bboxContains(p.bbox, match.bbox)
        );
        if (!para) continue;

        // Preserve style from the first span in the paragraph
        const firstSpan = para.lines[0]?.spans[0];
        const run: TextRun = {
          text: replacement,
          bold: firstSpan?.bold ?? false,
          italic: firstSpan?.italic ?? false,
          sizeScale: 1.0,
          color: firstSpan?.color ?? "#000000",
        };

        entries.push({
          type: "textEdit",
          pageId: match.pageId,
          spanIds: para.spanIds,
          newText: [run],
          overflowPolicy: "shrink",
        });
      }

      if (entries.length > 0) {
        onApplyReplacements(entries);
      }
    } finally {
      setApplying(false);
    }
  }, [matches, replacement, localExtractions, onApplyReplacements]);

  const selectedCount = matches.filter((m) => m.selected).length;
  const pageLabel = (m: SearchMatch) => {
    const pg = pages.find((p) => p.pageId === m.pageId);
    const idx = pages.indexOf(pg!);
    return idx >= 0 ? `Page ${idx + 1}` : m.pageId;
  };

  return (
    <div className="rounded-xl border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-900 w-80">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-2 dark:border-neutral-700">
        <span className="text-sm font-medium">Find &amp; Replace</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="rounded p-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={onClose}
            className="rounded p-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="p-3 flex flex-col gap-2">
          {/* Find */}
          <div className="flex gap-1">
            <input
              ref={queryRef}
              type="text"
              placeholder="Find…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-sm outline-none focus:border-blue-400 dark:border-neutral-700 dark:bg-neutral-800"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !query.trim()}
              className="flex items-center gap-1 rounded-lg bg-neutral-900 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-40 dark:bg-white dark:text-black"
            >
              <Search className="h-3 w-3" />
              {searching ? "…" : "Find"}
            </button>
          </div>

          {/* Replace */}
          <div className="flex gap-1">
            <input
              type="text"
              placeholder="Replace with…"
              value={replacement}
              onChange={(e) => setReplacement(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleApply()}
              className="flex-1 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-sm outline-none focus:border-blue-400 dark:border-neutral-700 dark:bg-neutral-800"
            />
            <button
              onClick={handleApply}
              disabled={applying || !selectedCount || !replacement}
              className="flex items-center gap-1 rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-40"
            >
              <Replace className="h-3 w-3" />
              {applying ? "…" : `Replace${selectedCount > 1 ? ` (${selectedCount})` : ""}`}
            </button>
          </div>

          {error && (
            <p className="flex items-center gap-1 text-xs text-red-500">
              <AlertTriangle className="h-3 w-3" />
              {error}
            </p>
          )}

          {/* Match list */}
          {matches.length > 0 && (
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs text-neutral-500">
                  {matches.length} match{matches.length !== 1 ? "es" : ""}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => toggleAll(true)}
                    className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                  >
                    All
                  </button>
                  <button
                    onClick={() => toggleAll(false)}
                    className="text-xs text-neutral-500 hover:underline"
                  >
                    None
                  </button>
                </div>
              </div>
              <ul className="max-h-40 overflow-y-auto rounded-lg border border-neutral-200 dark:border-neutral-700 divide-y divide-neutral-100 dark:divide-neutral-800">
                {matches.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={m.selected}
                      onChange={() => toggleMatch(m.id)}
                      className="h-3.5 w-3.5 accent-blue-600"
                    />
                    <span className="flex-1 truncate text-xs">
                      <span className="font-medium text-neutral-400">{pageLabel(m)}</span>
                      {" — "}
                      <span className="font-mono">{m.matchText}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {matches.length === 0 && !searching && query && (
            <p className="text-center text-xs text-neutral-400">No matches found.</p>
          )}
        </div>
      )}
    </div>
  );
}

function bboxContains(
  outer: [number, number, number, number],
  inner: [number, number, number, number],
  tol = 2
): boolean {
  return (
    outer[0] - tol <= inner[0] &&
    outer[1] - tol <= inner[1] &&
    outer[2] + tol >= inner[2] &&
    outer[3] + tol >= inner[3]
  );
}
