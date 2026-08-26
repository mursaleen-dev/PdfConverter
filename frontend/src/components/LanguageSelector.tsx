"use client";

import { Languages } from "lucide-react";
import { LANGUAGES, type Language, useI18n } from "@/lib/i18n";

export default function LanguageSelector() {
  const { language, setLanguage, t } = useI18n();
  return (
    <label className="fixed end-4 top-4 z-50 flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 py-2 shadow-sm dark:border-neutral-700 dark:bg-neutral-900">
      <Languages className="h-4 w-4 text-neutral-500" />
      <span className="sr-only">{t("common.language")}</span>
      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
        className="bg-transparent text-sm outline-none"
        aria-label={t("common.language")}
      >
        {LANGUAGES.map(([code, name]) => (
          <option key={code} value={code}>{name}</option>
        ))}
      </select>
    </label>
  );
}
