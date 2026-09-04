"use client";

import { useMemo, useState } from "react";
import CategoryTabs, { type Category } from "@/components/CategoryTabs";
import SearchBar from "@/components/SearchBar";
import ToolGrid from "@/components/ToolGrid";
import { tools } from "@/lib/tools";

export default function HomeTools() {
  const [activeCategory, setActiveCategory] = useState<Category>("All");
  const [query, setQuery] = useState("");

  const filteredTools = useMemo(() => {
    const byCategory =
      activeCategory === "All" ? tools : tools.filter((tool) => tool.category === "convert");

    const trimmedQuery = query.trim().toLowerCase();
    if (!trimmedQuery) return byCategory;

    return byCategory.filter((tool) => tool.title.toLowerCase().includes(trimmedQuery));
  }, [activeCategory, query]);

  return (
    <>
      <CategoryTabs active={activeCategory} onChange={setActiveCategory} />
      <SearchBar value={query} onChange={setQuery} />
      <ToolGrid tools={filteredTools} />
    </>
  );
}
