"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, X } from "lucide-react";
import ProgressBar from "@/components/ProgressBar";
import ConversionResult from "@/components/ConversionResult";
import { mergeFiles, ConvertError } from "@/lib/api";
import { MAX_FILE_SIZE_MB, getExtension } from "@/lib/constants";

type Status = "idle" | "uploading" | "success" | "error";

interface SuccessState {
  downloadUrl: string;
  filename: string;
}

export default function MergeFlow() {
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<SuccessState | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const accepted = Array.from(fileList).filter((f) => getExtension(f.name) === ".pdf");
    if (accepted.length === 0) {
      setErrorMessage("Please choose PDF files only.");
      return;
    }
    setErrorMessage("");
    setFiles((prev) => [...prev, ...accepted]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const moveFile = (index: number, direction: -1 | 1) => {
    setFiles((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const reset = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setFiles([]);
    setStatus("idle");
    setProgress(0);
    setErrorMessage("");
    setResult(null);
  };

  const handleMerge = async () => {
    if (files.length < 2) return;

    const totalSize = files.reduce((sum, f) => sum + f.size, 0);
    if (totalSize > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setErrorMessage(`Combined file size exceeds the maximum of ${MAX_FILE_SIZE_MB} MB.`);
      return;
    }

    setStatus("uploading");
    setProgress(0);
    setErrorMessage("");

    try {
      const { blob, filename } = await mergeFiles(files, setProgress);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setResult({ downloadUrl: url, filename });
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof ConvertError ? err.message : "Something went wrong. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  };

  return (
    <div className="flex flex-col items-center bg-transparent px-4 py-10 font-sans">
      <main className="flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
        <Link
          href="/"
          className="self-start inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to tools
        </Link>

        <div className="text-center">
          <h1 className="text-xl font-semibold">Merge PDF</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Combine multiple PDF files into one, in the order below
          </p>
        </div>

        {(status === "idle" || status === "error") && (
          <div className="flex w-full flex-col gap-4">
            <div
              onClick={() => inputRef.current?.click()}
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-neutral-300 p-6 text-center hover:border-neutral-400 dark:border-neutral-700 dark:hover:border-neutral-500"
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) => addFiles(e.target.files)}
              />
              <p className="text-sm font-medium">Click to add PDF files</p>
              <p className="text-xs text-neutral-500">Select 2 or more PDFs</p>
            </div>

            {files.length > 0 && (
              <ul className="flex flex-col gap-2">
                {files.map((file, index) => (
                  <li
                    key={`${file.name}-${index}`}
                    className="flex items-center gap-2 rounded-lg border border-neutral-200 px-3 py-2 text-sm dark:border-neutral-800"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-neutral-400" />
                    <span className="flex-1 truncate">{file.name}</span>
                    <button
                      type="button"
                      onClick={() => moveFile(index, -1)}
                      disabled={index === 0}
                      aria-label="Move up"
                      className="text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200"
                    >
                      &uarr;
                    </button>
                    <button
                      type="button"
                      onClick={() => moveFile(index, 1)}
                      disabled={index === files.length - 1}
                      aria-label="Move down"
                      className="text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200"
                    >
                      &darr;
                    </button>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      aria-label="Remove"
                      className="text-neutral-400 hover:text-red-600"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}

            <button
              onClick={handleMerge}
              disabled={files.length < 2}
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
            >
              {files.length >= 2 ? `Merge ${files.length} PDFs` : "Merge PDFs"}
            </button>
          </div>
        )}

        {status === "uploading" && (
          <div className="flex w-full flex-col items-center gap-3">
            <p className="text-sm text-neutral-500">Merging...</p>
            <ProgressBar percent={progress} />
          </div>
        )}

        {status === "success" && result && (
          <ConversionResult
            downloadUrl={result.downloadUrl}
            filename={result.filename}
            onReset={reset}
          />
        )}
      </main>
    </div>
  );
}
