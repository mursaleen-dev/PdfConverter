export const ACCEPTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".doc", ".docx"];

export const MAX_FILE_SIZE_MB = 20;

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function getExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx === -1 ? "" : filename.slice(idx).toLowerCase();
}

export function isAcceptedFile(file: File, acceptedExtensions: string[] = ACCEPTED_EXTENSIONS): boolean {
  return acceptedExtensions.includes(getExtension(file.name));
}
