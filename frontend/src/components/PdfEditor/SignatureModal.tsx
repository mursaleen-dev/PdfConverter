"use client";

import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Dancing_Script } from "next/font/google";
import { X } from "lucide-react";

const scriptFont = Dancing_Script({ subsets: ["latin"], weight: "700" });

type Tab = "draw" | "type" | "upload";

interface SignatureModalProps {
  onClose: () => void;
  onConfirm: (dataUrl: string) => void;
}

export default function SignatureModal({ onClose, onConfirm }: SignatureModalProps) {
  const [tab, setTab] = useState<Tab>("draw");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const [hasDrawn, setHasDrawn] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [uploadedDataUrl, setUploadedDataUrl] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || tab !== "draw") return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#111111";
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
  }, [tab]);

  const getPos = (e: PointerEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY };
  };

  const handlePointerDown = (e: PointerEvent<HTMLCanvasElement>) => {
    drawingRef.current = true;
    const ctx = canvasRef.current?.getContext("2d");
    const { x, y } = getPos(e);
    ctx?.beginPath();
    ctx?.moveTo(x, y);
  };

  const handlePointerMove = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    const { x, y } = getPos(e);
    ctx?.lineTo(x, y);
    ctx?.stroke();
    setHasDrawn(true);
  };

  const handlePointerUp = () => {
    drawingRef.current = false;
  };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (canvas && ctx) {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    setHasDrawn(false);
  };

  const handleUpload = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setUploadedDataUrl(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleConfirm = async () => {
    if (tab === "draw") {
      if (!hasDrawn || !canvasRef.current) return;
      onConfirm(canvasRef.current.toDataURL("image/png"));
      return;
    }

    if (tab === "type") {
      if (!typedName.trim()) return;
      await document.fonts.load(`700 56px ${scriptFont.style.fontFamily}`);
      const canvas = document.createElement("canvas");
      canvas.width = 480;
      canvas.height = 160;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#111111";
      ctx.font = `700 56px ${scriptFont.style.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(typedName.trim(), canvas.width / 2, canvas.height / 2);
      onConfirm(canvas.toDataURL("image/png"));
      return;
    }

    if (tab === "upload" && uploadedDataUrl) {
      onConfirm(uploadedDataUrl);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-neutral-950">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Add Signature</h2>
          <button onClick={onClose} aria-label="Close">
            <X className="h-5 w-5 text-neutral-500" />
          </button>
        </div>

        <div className="mb-4 flex gap-2">
          {(["draw", "type", "upload"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
                tab === t
                  ? "bg-neutral-900 text-white dark:bg-white dark:text-black"
                  : "border border-neutral-200 text-neutral-600 dark:border-neutral-800 dark:text-neutral-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === "draw" && (
          <div className="flex flex-col gap-2">
            <canvas
              ref={canvasRef}
              width={440}
              height={180}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerLeave={handlePointerUp}
              className="w-full touch-none rounded-lg border border-neutral-300 dark:border-neutral-700"
            />
            <button
              type="button"
              onClick={clearCanvas}
              className="self-start text-xs text-neutral-500 underline hover:text-neutral-700 dark:hover:text-neutral-300"
            >
              Clear
            </button>
          </div>
        )}

        {tab === "type" && (
          <div className="flex flex-col gap-3">
            <input
              type="text"
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              placeholder="Your name"
              className="rounded-lg border border-neutral-200 px-3 py-2 text-sm outline-none focus:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-950"
            />
            <div
              className={`${scriptFont.className} flex h-24 items-center justify-center rounded-lg border border-neutral-200 text-4xl text-neutral-900 dark:border-neutral-800 dark:text-neutral-50`}
            >
              {typedName || "Preview"}
            </div>
          </div>
        )}

        {tab === "upload" && (
          <div className="flex flex-col gap-3">
            <input
              type="file"
              accept="image/*"
              onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
            {uploadedDataUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={uploadedDataUrl}
                alt="Uploaded signature"
                className="h-24 w-full rounded-lg border border-neutral-200 object-contain dark:border-neutral-800"
              />
            )}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
          >
            Insert Signature
          </button>
        </div>
      </div>
    </div>
  );
}
