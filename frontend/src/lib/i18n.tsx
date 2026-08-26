"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export const LANGUAGES = [
  ["en", "English"],
  ["es", "Español"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["ar", "العربية"],
  ["ur", "اردو"],
  ["zh", "中文"],
] as const;

export type Language = (typeof LANGUAGES)[number][0];
type Messages = Record<string, string>;

const en: Messages = {
  "home.title": "Every tool you need for your files",
  "home.subtitle": "Convert, organize, and manage your PDFs, in one place.",
  "common.all": "All",
  "common.convertPdf": "Convert PDF",
  "common.search": "Search tools...",
  "common.back": "Back to tools",
  "common.drag": "Drag & drop a file here, or click to browse",
  "common.accepted": "Accepted",
  "common.converting": "Converting...",
  "common.tryAgain": "Try again",
  "common.complete": "Conversion complete",
  "common.download": "Download",
  "common.another": "Convert another file",
  "common.mode": "Conversion mode",
  "common.language": "Language",
  "common.toolDescription": "Process your files quickly and securely.",
};

const titles: Record<string, string> = {
  "merge-pdf": "Merge PDF", "edit-pdf": "Edit PDF", "pdf-to-word": "PDF to Word",
  "word-to-pdf": "Word to PDF", "pdf-to-excel": "PDF to Excel", "excel-to-pdf": "Excel to PDF",
  "pdf-to-powerpoint": "PDF to PowerPoint", "powerpoint-to-pdf": "PowerPoint to PDF",
  "pdf-to-jpg": "PDF to JPG", "jpg-to-pdf": "JPG to PDF", "png-to-pdf": "PNG to PDF",
  "pdf-to-png": "PDF to PNG", "html-to-pdf": "HTML to PDF", "pdf-to-text": "PDF to Text",
  "text-to-pdf": "Text to PDF", "pdf-to-pdfa": "PDF to PDF/A",
};
Object.entries(titles).forEach(([id, title]) => { en[`tool.${id}`] = title; });

const dictionaries: Record<Language, Messages> = {
  en,
  es: {
    "home.title": "Todas las herramientas que necesitas para tus archivos",
    "home.subtitle": "Convierte, organiza y administra tus PDF en un solo lugar.",
    "common.all": "Todo", "common.convertPdf": "Convertir PDF", "common.search": "Buscar herramientas...",
    "common.back": "Volver a herramientas", "common.drag": "Arrastra un archivo aquí o haz clic para buscar",
    "common.accepted": "Aceptado", "common.converting": "Convirtiendo...", "common.tryAgain": "Intentar de nuevo",
    "common.complete": "Conversión completada", "common.download": "Descargar",
    "common.another": "Convertir otro archivo", "common.mode": "Modo de conversión", "common.language": "Idioma", "common.toolDescription": "Procesa tus archivos de forma rápida y segura.",
  },
  fr: {
    "home.title": "Tous les outils dont vous avez besoin pour vos fichiers",
    "home.subtitle": "Convertissez, organisez et gérez vos PDF au même endroit.",
    "common.all": "Tous", "common.convertPdf": "Convertir PDF", "common.search": "Rechercher des outils...",
    "common.back": "Retour aux outils", "common.drag": "Glissez un fichier ici ou cliquez pour parcourir",
    "common.accepted": "Accepté", "common.converting": "Conversion...", "common.tryAgain": "Réessayer",
    "common.complete": "Conversion terminée", "common.download": "Télécharger",
    "common.another": "Convertir un autre fichier", "common.mode": "Mode de conversion", "common.language": "Langue", "common.toolDescription": "Traitez vos fichiers rapidement et en toute sécurité.",
  },
  de: {
    "home.title": "Alle Werkzeuge für Ihre Dateien",
    "home.subtitle": "PDFs an einem Ort konvertieren, organisieren und verwalten.",
    "common.all": "Alle", "common.convertPdf": "PDF konvertieren", "common.search": "Werkzeuge suchen...",
    "common.back": "Zurück zu den Werkzeugen", "common.drag": "Datei hier ablegen oder zum Auswählen klicken",
    "common.accepted": "Akzeptiert", "common.converting": "Wird konvertiert...", "common.tryAgain": "Erneut versuchen",
    "common.complete": "Konvertierung abgeschlossen", "common.download": "Herunterladen",
    "common.another": "Weitere Datei konvertieren", "common.mode": "Konvertierungsmodus", "common.language": "Sprache", "common.toolDescription": "Dateien schnell und sicher verarbeiten.",
  },
  ar: {
    "home.title": "كل الأدوات التي تحتاجها لملفاتك",
    "home.subtitle": "حوّل ونظّم وأدر ملفات PDF في مكان واحد.",
    "common.all": "الكل", "common.convertPdf": "تحويل PDF", "common.search": "البحث عن أدوات...",
    "common.back": "العودة إلى الأدوات", "common.drag": "اسحب ملفاً هنا أو انقر للاختيار",
    "common.accepted": "الملفات المقبولة", "common.converting": "جارٍ التحويل...", "common.tryAgain": "حاول مرة أخرى",
    "common.complete": "اكتمل التحويل", "common.download": "تنزيل",
    "common.another": "تحويل ملف آخر", "common.mode": "وضع التحويل", "common.language": "اللغة", "common.toolDescription": "عالج ملفاتك بسرعة وأمان.",
  },
  ur: {
    "home.title": "آپ کی فائلوں کے لیے تمام ضروری ٹولز",
    "home.subtitle": "PDF فائلوں کو ایک جگہ تبدیل، منظم اور کنٹرول کریں۔",
    "common.all": "سب", "common.convertPdf": "PDF تبدیل کریں", "common.search": "ٹولز تلاش کریں...",
    "common.back": "ٹولز پر واپس جائیں", "common.drag": "فائل یہاں کھینچیں یا منتخب کرنے کے لیے کلک کریں",
    "common.accepted": "قابل قبول", "common.converting": "تبدیل ہو رہا ہے...", "common.tryAgain": "دوبارہ کوشش کریں",
    "common.complete": "تبدیلی مکمل", "common.download": "ڈاؤن لوڈ",
    "common.another": "دوسری فائل تبدیل کریں", "common.mode": "تبدیلی کا طریقہ", "common.language": "زبان", "common.toolDescription": "اپنی فائلیں تیزی اور محفوظ طریقے سے پروسیس کریں۔",
  },
  zh: {
    "home.title": "文件处理所需的全部工具",
    "home.subtitle": "在一个地方转换、整理和管理 PDF。",
    "common.all": "全部", "common.convertPdf": "转换 PDF", "common.search": "搜索工具...",
    "common.back": "返回工具", "common.drag": "将文件拖到此处，或点击浏览",
    "common.accepted": "支持格式", "common.converting": "正在转换...", "common.tryAgain": "重试",
    "common.complete": "转换完成", "common.download": "下载",
    "common.another": "转换其他文件", "common.mode": "转换模式", "common.language": "语言", "common.toolDescription": "快速、安全地处理您的文件。",
  },
};

const titleTranslations: Record<Exclude<Language, "en">, Record<string, string>> = {
  es: { "merge-pdf":"Unir PDF","edit-pdf":"Editar PDF","pdf-to-word":"PDF a Word","word-to-pdf":"Word a PDF","pdf-to-excel":"PDF a Excel","excel-to-pdf":"Excel a PDF","pdf-to-powerpoint":"PDF a PowerPoint","powerpoint-to-pdf":"PowerPoint a PDF","pdf-to-jpg":"PDF a JPG","jpg-to-pdf":"JPG a PDF","png-to-pdf":"PNG a PDF","pdf-to-png":"PDF a PNG","html-to-pdf":"HTML a PDF","pdf-to-text":"PDF a texto","text-to-pdf":"Texto a PDF","pdf-to-pdfa":"PDF a PDF/A" },
  fr: { "merge-pdf":"Fusionner PDF","edit-pdf":"Modifier PDF","pdf-to-word":"PDF vers Word","word-to-pdf":"Word vers PDF","pdf-to-excel":"PDF vers Excel","excel-to-pdf":"Excel vers PDF","pdf-to-powerpoint":"PDF vers PowerPoint","powerpoint-to-pdf":"PowerPoint vers PDF","pdf-to-jpg":"PDF vers JPG","jpg-to-pdf":"JPG vers PDF","png-to-pdf":"PNG vers PDF","pdf-to-png":"PDF vers PNG","html-to-pdf":"HTML vers PDF","pdf-to-text":"PDF vers texte","text-to-pdf":"Texte vers PDF","pdf-to-pdfa":"PDF vers PDF/A" },
  de: { "merge-pdf":"PDF zusammenfügen","edit-pdf":"PDF bearbeiten","pdf-to-word":"PDF zu Word","word-to-pdf":"Word zu PDF","pdf-to-excel":"PDF zu Excel","excel-to-pdf":"Excel zu PDF","pdf-to-powerpoint":"PDF zu PowerPoint","powerpoint-to-pdf":"PowerPoint zu PDF","pdf-to-jpg":"PDF zu JPG","jpg-to-pdf":"JPG zu PDF","png-to-pdf":"PNG zu PDF","pdf-to-png":"PDF zu PNG","html-to-pdf":"HTML zu PDF","pdf-to-text":"PDF zu Text","text-to-pdf":"Text zu PDF","pdf-to-pdfa":"PDF zu PDF/A" },
  ar: { "merge-pdf":"دمج PDF","edit-pdf":"تحرير PDF","pdf-to-word":"PDF إلى Word","word-to-pdf":"Word إلى PDF","pdf-to-excel":"PDF إلى Excel","excel-to-pdf":"Excel إلى PDF","pdf-to-powerpoint":"PDF إلى PowerPoint","powerpoint-to-pdf":"PowerPoint إلى PDF","pdf-to-jpg":"PDF إلى JPG","jpg-to-pdf":"JPG إلى PDF","png-to-pdf":"PNG إلى PDF","pdf-to-png":"PDF إلى PNG","html-to-pdf":"HTML إلى PDF","pdf-to-text":"PDF إلى نص","text-to-pdf":"نص إلى PDF","pdf-to-pdfa":"PDF إلى PDF/A" },
  ur: { "merge-pdf":"PDF ضم کریں","edit-pdf":"PDF میں ترمیم","pdf-to-word":"PDF سے Word","word-to-pdf":"Word سے PDF","pdf-to-excel":"PDF سے Excel","excel-to-pdf":"Excel سے PDF","pdf-to-powerpoint":"PDF سے PowerPoint","powerpoint-to-pdf":"PowerPoint سے PDF","pdf-to-jpg":"PDF سے JPG","jpg-to-pdf":"JPG سے PDF","png-to-pdf":"PNG سے PDF","pdf-to-png":"PDF سے PNG","html-to-pdf":"HTML سے PDF","pdf-to-text":"PDF سے متن","text-to-pdf":"متن سے PDF","pdf-to-pdfa":"PDF سے PDF/A" },
  zh: { "merge-pdf":"合并 PDF","edit-pdf":"编辑 PDF","pdf-to-word":"PDF 转 Word","word-to-pdf":"Word 转 PDF","pdf-to-excel":"PDF 转 Excel","excel-to-pdf":"Excel 转 PDF","pdf-to-powerpoint":"PDF 转 PowerPoint","powerpoint-to-pdf":"PowerPoint 转 PDF","pdf-to-jpg":"PDF 转 JPG","jpg-to-pdf":"JPG 转 PDF","png-to-pdf":"PNG 转 PDF","pdf-to-png":"PDF 转 PNG","html-to-pdf":"HTML 转 PDF","pdf-to-text":"PDF 转文本","text-to-pdf":"文本转 PDF","pdf-to-pdfa":"PDF 转 PDF/A" },
};
for (const [language, values] of Object.entries(titleTranslations)) {
  for (const [id, title] of Object.entries(values)) dictionaries[language as Language][`tool.${id}`] = title;
}

interface I18nValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, fallback?: string) => string;
}
const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");
  useEffect(() => {
    const saved = localStorage.getItem("app-language") as Language | null;
    if (saved && LANGUAGES.some(([code]) => code === saved)) setLanguageState(saved);
  }, []);
  const setLanguage = (next: Language) => {
    setLanguageState(next);
    localStorage.setItem("app-language", next);
  };
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" || language === "ur" ? "rtl" : "ltr";
  }, [language]);
  const value = useMemo<I18nValue>(() => ({
    language,
    setLanguage,
    t: (key, fallback) => dictionaries[language][key] ?? en[key] ?? fallback ?? key,
  }), [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
