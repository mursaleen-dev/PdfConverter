"use client";

import { useCallback, useRef } from "react";
import type { ExtractedPage } from "./types";
import { extractPage } from "@/lib/api";

export interface TextExtractHook {
  getPage: (
    file: File,
    pageId: string,
    sourceIndex: number
  ) => Promise<ExtractedPage | null>;
  extractAll: (
    file: File,
    pages: Array<{ pageId: string; sourceIndex: number }>
  ) => Promise<Map<string, ExtractedPage>>;
  invalidate: (pageId: string) => void;
  clear: () => void;
}

/**
 * Lazy, cached per-page text extraction.
 * Re-uses the same result across renders until invalidated.
 */
export function useTextExtract(): TextExtractHook {
  const cache = useRef<Map<string, ExtractedPage>>(new Map());
  const inflight = useRef<Map<string, Promise<ExtractedPage | null>>>(new Map());

  const getPage = useCallback(
    async (
      file: File,
      pageId: string,
      sourceIndex: number
    ): Promise<ExtractedPage | null> => {
      if (cache.current.has(pageId)) {
        return cache.current.get(pageId)!;
      }
      if (inflight.current.has(pageId)) {
        return inflight.current.get(pageId)!;
      }

      const promise = extractPage(file, pageId, sourceIndex)
        .then((page) => {
          cache.current.set(pageId, page);
          inflight.current.delete(pageId);
          return page;
        })
        .catch(() => {
          inflight.current.delete(pageId);
          return null;
        });

      inflight.current.set(pageId, promise);
      return promise;
    },
    []
  );

  const extractAll = useCallback(
    async (
      file: File,
      pages: Array<{ pageId: string; sourceIndex: number }>
    ): Promise<Map<string, ExtractedPage>> => {
      const results = await Promise.all(
        pages.map((p) =>
          getPage(file, p.pageId, p.sourceIndex).then(
            (ep) => (ep ? ([p.pageId, ep] as const) : null)
          )
        )
      );
      const map = new Map<string, ExtractedPage>();
      for (const r of results) {
        if (r) map.set(r[0], r[1]);
      }
      return map;
    },
    [getPage]
  );

  const invalidate = useCallback((pageId: string) => {
    cache.current.delete(pageId);
  }, []);

  const clear = useCallback(() => {
    cache.current.clear();
    inflight.current.clear();
  }, []);

  return { getPage, extractAll, invalidate, clear };
}
