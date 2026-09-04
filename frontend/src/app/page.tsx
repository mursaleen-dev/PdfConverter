import HomeTools from "@/components/HomeTools";
import JsonLd from "@/components/JsonLd";
import { HOME_SEO } from "@/lib/seo-content";
import { softwareJsonLd, websiteJsonLd } from "@/lib/seo";
import { SITE_NAME } from "@/lib/site";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-zinc-50 px-4 py-12 font-sans dark:bg-black sm:px-8">
      <JsonLd data={[websiteJsonLd(), softwareJsonLd()]} />
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="text-center">
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 sm:text-3xl">
            {HOME_SEO.metaTitle}
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">
            {HOME_SEO.intro}
          </p>
        </header>
        <HomeTools />
        <p className="text-center text-xs text-neutral-400">
          {SITE_NAME} runs in your browser. Open a tool, upload a file, and download the result.
        </p>
      </div>
    </div>
  );
}
