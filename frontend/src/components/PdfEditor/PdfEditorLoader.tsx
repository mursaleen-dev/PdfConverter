"use client";

import dynamic from "next/dynamic";

const PdfEditor = dynamic(() => import("./PdfEditor"), {
  ssr: false,
  loading: () => (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 py-24 text-sm text-neutral-500 dark:bg-black">
      Loading editor...
    </div>
  ),
});

export default function PdfEditorLoader() {
  return <PdfEditor />;
}
