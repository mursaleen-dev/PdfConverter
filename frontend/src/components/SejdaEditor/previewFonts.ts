/** Prefix so injected edit fonts never collide with pdf.js page rasterization. */
export const PREVIEW_FONT_PREFIX = "PdfEdit__";

export function cleanFontFamily(fontName: string): string {
  return fontName
    .replace(/^[A-Z]{6}\+/, "")
    .replace(/[^A-Za-z0-9 _-]/g, "")
    .trim();
}

export function previewFontFamily(fontName: string): string {
  const family = cleanFontFamily(fontName);
  if (!family) return "";
  return family.startsWith(PREVIEW_FONT_PREFIX)
    ? family
    : `${PREVIEW_FONT_PREFIX}${family}`;
}

export function cssFontWeight(span: {
  fontWeight?: number;
  bold?: boolean;
} | null | undefined): number {
  if (span?.fontWeight && span.fontWeight > 0) return span.fontWeight;
  return span?.bold ? 700 : 400;
}

export function cssFontStack(fontName: string): string {
  const original = cleanFontFamily(fontName);
  if (!original) return "sans-serif";
  const preview = previewFontFamily(original);
  if (preview === original) {
    return `"${original}", sans-serif`;
  }
  // Namespaced preview face first; original family next so a missing FontFace
  // still uses the PDF's family instead of substituting Arial.
  return `"${preview}", "${original}", sans-serif`;
}
