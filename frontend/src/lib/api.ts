import { API_BASE_URL } from "./constants";

export interface ConvertSuccess {
  blob: Blob;
  filename: string;
  warnings?: string[];
}

export class ConvertError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

function extractFilename(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  // RFC 5987 encoded: filename*=utf-8''name.ext  (preferred, handles non-ASCII)
  const rfc5987 = /filename\*=utf-8''([^;]+)/i.exec(disposition);
  if (rfc5987) return decodeURIComponent(rfc5987[1]);
  // Plain quoted or unquoted: filename="name.ext"
  const plain = /filename="?([^";]+)"?/.exec(disposition);
  return plain ? plain[1] : fallback;
}

async function parseBlobError(blob: Blob): Promise<ConvertError> {
  try {
    const text = await blob.text();
    const parsed = JSON.parse(text);
    // FastAPI returns {"detail":"..."} — older code read parsed.error/parsed.message (always undefined)
    const message =
      typeof parsed.detail === "string"
        ? parsed.detail
        : (parsed.message ?? parsed.error ?? "Conversion failed.");
    return new ConvertError(parsed.code ?? "server_error", message);
  } catch {
    return new ConvertError("unknown_error", "Conversion failed. Please try again.");
  }
}

function sendFormData(
  formData: FormData,
  path: string,
  fallbackFilename: string,
  onProgress?: (percent: number) => void
): Promise<ConvertSuccess> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    xhr.responseType = "blob";

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
    }

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const blob = xhr.response as Blob;
        const filename = extractFilename(xhr.getResponseHeader("Content-Disposition"), fallbackFilename);
        const warnHeader = xhr.getResponseHeader("X-Sejda-Warnings");
        let warnings: string[] | undefined;
        if (warnHeader) {
          try { warnings = JSON.parse(warnHeader) as string[]; } catch { /* ignore malformed header */ }
        }
        resolve({ blob, filename, warnings });
        return;
      }
      reject(await parseBlobError(xhr.response as Blob));
    };

    xhr.onerror = () => {
      reject(new ConvertError("network_error", "Could not reach the server. Is the backend running?"));
    };

    xhr.send(formData);
  });
}

export function convertFile(
  file: File,
  toolId: string,
  onProgress: (percent: number) => void,
  options?: { mode?: string }
): Promise<ConvertSuccess> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("tool", toolId);
  if (options?.mode) formData.append("mode", options.mode);
  return sendFormData(formData, "/api/convert", "converted.pdf", onProgress);
}

export function mergeFiles(files: File[], onProgress: (percent: number) => void): Promise<ConvertSuccess> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return sendFormData(formData, "/api/merge", "merged.pdf", onProgress);
}

export interface EditElementPayload {
  page: number;
  type: "text" | "image";
  x: number;
  y: number;
  width: number;
  height: number;
  // Text element — fontSize is in PDF points (already divided by render scale)
  text?: string;
  fontSize?: number;
  fontFamily?: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  color?: string;
  // Image element
  image?: string;
}

/** One in-place text replacement: redact the original span and reinsert
 *  new text with the detected style from the original PDF. */
export interface TextReplacementPayload {
  page: number;       // 0-indexed (backend convention)
  x0: number;         // PDF point coordinates of the original span bbox
  y0: number;
  x1: number;
  y1: number;
  new_text: string;
  // Exact PDF-space (y-up) baseline Y.  When provided the backend uses
  // insert_text() at this coordinate instead of insert_textbox() with a
  // padded rect estimate, giving pixel-accurate vertical placement.
  baseline_y: number;
}

export function editPdf(
  file: File,
  elements: EditElementPayload[],
  onProgress: (percent: number) => void,
  textReplacements?: TextReplacementPayload[]
): Promise<ConvertSuccess> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("elements", JSON.stringify(elements));
  if (textReplacements && textReplacements.length > 0) {
    formData.append("text_replacements", JSON.stringify(textReplacements));
  }
  return sendFormData(formData, "/api/edit", "edited.pdf", onProgress);
}

export function applySejdaManifest(
  file: File,
  manifest: import("@/components/SejdaEditor/types").ManifestObject[],
  pageOps?: import("@/components/SejdaEditor/types").PageDescriptor[],
  textEdits?: import("@/components/SejdaEditor/types").TextEditEntry[],
  onProgress?: (percent: number) => void
): Promise<ConvertSuccess> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("manifest", JSON.stringify(manifest));
  if (pageOps) formData.append("page_ops", JSON.stringify(pageOps));
  if (textEdits && textEdits.length > 0) formData.append("text_edits", JSON.stringify(textEdits));
  return sendFormData(formData, "/api/sejda", "edited.pdf", onProgress);
}

export async function extractPage(
  file: File,
  pageId: string,
  sourceIndex: number
): Promise<import("@/components/SejdaEditor/types").ExtractedPage> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("page_id", pageId);
  formData.append("source_index", String(sourceIndex));

  const response = await fetch(`${API_BASE_URL}/api/sejda/extract-page`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ConvertError("extraction_failed", `Extraction failed: ${text}`);
  }
  return response.json();
}

export async function preflightEdit(
  file: File,
  params: {
    sourceIndex: number;
    pageId: string;
    spanIds: string[];
    runs: import("@/components/SejdaEditor/types").TextRun[];
    overflowPolicy: string;
    availableWidth: number;
    domSize: number;
    fontName: string;
    bold: boolean;
    italic: boolean;
  }
): Promise<import("@/components/SejdaEditor/types").PreflightResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source_index", String(params.sourceIndex));
  formData.append("page_id", params.pageId);
  formData.append("span_ids_json", JSON.stringify(params.spanIds));
  formData.append("runs_json", JSON.stringify(params.runs));
  formData.append("overflow_policy", params.overflowPolicy);
  formData.append("available_width", String(params.availableWidth));
  formData.append("dom_size", String(params.domSize));
  formData.append("font_name", params.fontName);
  formData.append("bold", params.bold ? "true" : "false");
  formData.append("italic", params.italic ? "true" : "false");

  const response = await fetch(`${API_BASE_URL}/api/sejda/preflight-edit`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new ConvertError("preflight_failed", "Preflight check failed.");
  }
  return response.json();
}

export async function searchText(
  file: File,
  query: string,
  pageScope?: { sourceIndex: number; pageId: string }[]
): Promise<import("@/components/SejdaEditor/types").SearchMatch[]> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("query", query);
  if (pageScope) formData.append("page_scope_json", JSON.stringify(pageScope));

  const response = await fetch(`${API_BASE_URL}/api/sejda/search`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new ConvertError("search_failed", "Search failed.");
  }
  const data = await response.json();
  return data.matches ?? [];
}

export async function convertUrl(url: string): Promise<ConvertSuccess> {
  const response = await fetch(`${API_BASE_URL}/api/convert-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    throw await parseBlobError(await response.blob());
  }

  const blob = await response.blob();
  const filename = extractFilename(response.headers.get("Content-Disposition"), "webpage.pdf");
  return { blob, filename };
}
