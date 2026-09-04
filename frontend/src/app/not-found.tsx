import Link from "next/link";
import { SITE_NAME } from "@/lib/site";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 py-16 font-sans">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="max-w-md text-center text-sm text-neutral-500">
        That URL is not a {SITE_NAME} converter. Go back to the tool list to edit, merge, or
        convert a PDF.
      </p>
      <Link
        href="/"
        className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
      >
        All PDF tools
      </Link>
    </div>
  );
}
