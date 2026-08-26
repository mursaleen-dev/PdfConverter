"use client";

import { useMemo, useState } from "react";
import CategoryTabs, { type Category } from "@/components/CategoryTabs";
import SearchBar from "@/components/SearchBar";
import ToolGrid from "@/components/ToolGrid";
import { tools } from "@/lib/tools";
import { useI18n } from "@/lib/i18n";

export default function Home() {
  const [activeCategory, setActiveCategory] = useState<Category>("All");
  const [query, setQuery] = useState("");
  const { t } = useI18n();

  const filteredTools = useMemo(() => {
    const byCategory =
      activeCategory === "All" ? tools : tools.filter((tool) => tool.category === "convert");

    const trimmedQuery = query.trim().toLowerCase();
    if (!trimmedQuery) return byCategory;

    return byCategory.filter((tool) => tool.title.toLowerCase().includes(trimmedQuery));
  }, [activeCategory, query]);

  return (
    <div className="flex flex-1 flex-col bg-zinc-50 px-4 py-12 font-sans dark:bg-black sm:px-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 sm:text-3xl">
            {t("home.title")}
          </h1>
          <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
            {t("home.subtitle")}
          </p>
        </div>

        <CategoryTabs active={activeCategory} onChange={setActiveCategory} />
        <SearchBar value={query} onChange={setQuery} />
        <ToolGrid tools={filteredTools} />
      </div>
    </div>
  );
}
