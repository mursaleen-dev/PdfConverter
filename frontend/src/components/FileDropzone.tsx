"use client";

import { useRef, useState } from "react";

interface FileDropzoneProps {
  onFileSelected: (file: File) => void;
  acceptedExtensions: string[];
  disabled?: boolean;
}

export default function FileDropzone({ onFileSelected, acceptedExtensions, disabled }: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    onFileSelected(files[0]);
  };

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        if (!disabled) handleFiles(e.dataTransfer.files);
      }}
      className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
        disabled
          ? "cursor-not-allowed border-neutral-300 opacity-60 dark:border-neutral-700"
          : "cursor-pointer border-neutral-300 hover:border-neutral-400 dark:border-neutral-700 dark:hover:border-neutral-500"
      } ${isDragging ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={acceptedExtensions.join(",")}
        className="hidden"
        disabled={disabled}
        onChange={(e) => handleFiles(e.target.files)}
      />
      <p className="text-sm font-medium">
        Drag &amp; drop a file here, or click to browse
      </p>
      <p className="text-xs text-neutral-500">
        Accepted: {acceptedExtensions.join(", ")}
      </p>
    </div>
  );
}
