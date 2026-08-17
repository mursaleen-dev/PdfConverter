"use client";
import { useI18n } from "@/lib/i18n";

export type Category = "All" | "Convert PDF";

const CATEGORIES: Category[] = ["All", "Convert PDF"];

interface CategoryTabsProps {
  active: Category;
  onChange: (category: Category) => void;
}

export default function CategoryTabs({ active, onChange }: CategoryTabsProps) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {CATEGORIES.map((category) => {
        const isActive = category === active;
        return (
          <button
            key={category}
            onClick={() => onChange(category)}
            className={`rounded-full px-5 py-2 text-sm font-medium transition-all duration-200 ${
              isActive
                ? "bg-neutral-900 text-white shadow-sm dark:bg-white dark:text-black"
                : "border border-neutral-200 bg-white text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-950 dark:text-neutral-300 dark:hover:bg-neutral-900"
            }`}
          >
            {category === "All" ? t("common.all") : t("common.convertPdf")}
          </button>
        );
      })}
    </div>
  );
}
