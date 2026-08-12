"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import FileDropzone from "@/components/FileDropzone";
import ProgressBar from "@/components/ProgressBar";
import ConversionResult from "@/components/ConversionResult";
import { convertFile, ConvertError } from "@/lib/api";
import { MAX_FILE_SIZE_MB, isAcceptedFile } from "@/lib/constants";

type Status = "idle" | "uploading" | "success" | "error";

interface SuccessState {
  downloadUrl: string;
  filename: string;
}

interface ConverterFlowProps {
  toolId: string;
  title: string;
  description: string;
  acceptedExtensions: string[];
  unsupportedMessage: string;
  conversionModes?: {
    value: string;
    label: string;
    description: string;
  }[];
}

export default function ConverterFlow({
  toolId,
  title,
  description,
  acceptedExtensions,
  unsupportedMessage,
  conversionModes,
}: ConverterFlowProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<SuccessState | null>(null);
  const [conversionMode, setConversionMode] = useState(
    conversionModes?.[0]?.value ?? ""
  );
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
    setStatus("idle");
    setProgress(0);
    setErrorMessage("");
    setResult(null);
  };

  const handleFileSelected = async (file: File) => {
    if (!isAcceptedFile(file, acceptedExtensions)) {
      setStatus("error");
      setErrorMessage(unsupportedMessage);
      return;
    }

    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setStatus("error");
      setErrorMessage(`File exceeds the maximum allowed size of ${MAX_FILE_SIZE_MB} MB.`);
      return;
    }

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }

    setStatus("uploading");
    setProgress(0);
    setErrorMessage("");
    setResult(null);

    try {
      const { blob, filename } = await convertFile(file, toolId, setProgress, {
        mode: conversionMode || undefined,
      });
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
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-4 font-sans dark:bg-black">
      <main className="flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
        <Link
          href="/"
          className="self-start inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to tools
        </Link>

        <div className="text-center">
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-neutral-500">{description}</p>
        </div>

        {status === "idle" && (
          <>
            {conversionModes && conversionModes.length > 0 && (
              <fieldset className="w-full">
                <legend className="mb-2 text-sm font-medium">Conversion mode</legend>
                <div className="grid gap-2">
                  {conversionModes.map((mode) => {
                    const selected = conversionMode === mode.value;
                    return (
                      <label
                        key={mode.value}
                        className={`cursor-pointer rounded-xl border p-3 transition ${
                          selected
                            ? "border-blue-600 bg-blue-50 dark:border-blue-400 dark:bg-blue-950/40"
                            : "border-neutral-200 hover:border-neutral-400 dark:border-neutral-800"
                        }`}
                      >
                        <input
                          type="radio"
                          name="conversion-mode"
                          value={mode.value}
                          checked={selected}
                          onChange={() => setConversionMode(mode.value)}
                          className="sr-only"
                        />
                        <span className="block text-sm font-medium">{mode.label}</span>
                        <span className="mt-0.5 block text-xs text-neutral-500">
                          {mode.description}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            )}
            <FileDropzone
              onFileSelected={handleFileSelected}
              acceptedExtensions={acceptedExtensions}
            />
          </>
        )}

        {status === "uploading" && (
          <div className="flex w-full flex-col items-center gap-3">
            <p className="text-sm text-neutral-500">Converting...</p>
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

        {status === "error" && (
          <div className="flex w-full flex-col items-center gap-3 text-center">
            <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
            <button
              onClick={reset}
              className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
            >
              Try again
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
