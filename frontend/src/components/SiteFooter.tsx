import Link from "next/link";
import { tools } from "@/lib/tools";
import { SITE_NAME } from "@/lib/site";

export default function SiteFooter() {
  const implemented = tools.filter((tool) => tool.implemented && tool.href);

  return (
    <footer className="border-t border-neutral-200 bg-white px-4 py-8 font-sans text-sm dark:border-neutral-800 dark:bg-neutral-950">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <p className="font-semibold text-neutral-900 dark:text-neutral-50">{SITE_NAME}</p>
        <nav aria-label="PDF tools">
          <ul className="flex flex-wrap gap-x-4 gap-y-2">
            {implemented.map((tool) => (
              <li key={tool.id}>
                <Link
                  href={tool.href!}
                  className="text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
                >
                  {tool.title}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <p className="text-xs text-neutral-400">
          Online PDF editor and converters. Files are processed for your download; they are not
          published as a public gallery.
        </p>
      </div>
    </footer>
  );
}
