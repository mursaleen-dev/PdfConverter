"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import ConversionResult from "@/components/ConversionResult";
import { convertUrl, ConvertError } from "@/lib/api";

type Status = "idle" | "loading" | "success" | "error";

interface SuccessState {
  downloadUrl: string;
  filename: string;
}

export default function UrlConvertFlow() {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<SuccessState | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const reset = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setUrl("");
    setStatus("idle");
    setErrorMessage("");
    setResult(null);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setStatus("loading");
    setErrorMessage("");

    try {
      const { blob, filename } = await convertUrl(url.trim());
      const objectUrl = URL.createObjectURL(blob);
      objectUrlRef.current = objectUrl;
      setResult({ downloadUrl: objectUrl, filename });
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
          <h1 className="text-xl font-semibold">HTML to PDF</h1>
          <p className="mt-1 text-sm text-neutral-500">Paste a URL to convert that page to PDF</p>
        </div>

        {status !== "success" && (
          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-3">
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              disabled={status === "loading"}
              className="w-full rounded-lg border border-neutral-200 bg-white px-4 py-2.5 text-sm outline-none focus:border-neutral-400 disabled:opacity-60 dark:border-neutral-800 dark:bg-neutral-950 dark:focus:border-neutral-600"
            />
            {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
            <button
              type="submit"
              disabled={status === "loading" || !url.trim()}
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
            >
              {status === "loading" ? "Converting..." : "Convert to PDF"}
            </button>
          </form>
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
