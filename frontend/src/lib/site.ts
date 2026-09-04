export const SITE_NAME =
  process.env.NEXT_PUBLIC_SITE_NAME?.trim() || "PDF Tools";

export const SITE_TAGLINE =
  "Edit, convert, and merge PDFs in the browser — keep original fonts, layouts, and pages.";

export function getSiteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, "");
  const vercel = process.env.VERCEL_URL?.trim();
  if (vercel) return `https://${vercel.replace(/\/$/, "")}`;
  return "http://localhost:3000";
}
