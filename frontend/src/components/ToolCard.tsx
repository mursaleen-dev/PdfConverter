import Link from "next/link";
import type { Tool } from "@/lib/tools";

interface ToolCardProps {
  tool: Tool;
}

export default function ToolCard({ tool }: ToolCardProps) {
  const Icon = tool.icon;

  const iconEl = (
    <div
      className={`flex h-11 w-11 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-110 ${tool.color}`}
    >
      <Icon className="h-5 w-5" />
    </div>
  );

  const body = (
    <>
      {iconEl}
      <h3 className="mt-4 text-base font-semibold text-neutral-900 dark:text-neutral-50">
        {tool.title}
      </h3>
      <p className="mt-1.5 text-sm leading-snug text-neutral-500 dark:text-neutral-400">
        {tool.description}
      </p>
    </>
  );

  if (!tool.implemented) {
    return (
      <div
        aria-disabled="true"
        className="group relative flex cursor-not-allowed flex-col rounded-2xl border border-neutral-200 bg-white p-5 opacity-70 dark:border-neutral-800 dark:bg-neutral-950"
      >
        <span className="absolute right-4 top-4 rounded-full bg-neutral-100 px-2.5 py-1 text-[11px] font-medium text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
          Coming Soon
        </span>
        {body}
      </div>
    );
  }

  return (
    <Link
      href={tool.href ?? "#"}
      className="group flex cursor-pointer flex-col rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-blue-400 hover:shadow-lg dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-blue-500"
    >
      {body}
    </Link>
  );
}
