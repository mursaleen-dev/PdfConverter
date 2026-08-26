"use client";

import dynamic from "next/dynamic";

const SejdaEditor = dynamic(() => import("./SejdaEditor"), { ssr: false });

export default function SejdaEditorLoader() {
  return <SejdaEditor />;
}
