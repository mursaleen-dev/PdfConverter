import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import { getToolSeo, TOOL_SEO } from "@/lib/seo-content";
import { toolJsonLd } from "@/lib/seo";

export default function ToolSeoContent({ toolId }: { toolId: string }) {
  const tool = getToolSeo(toolId);
  const related = tool.related
    .map((id) => TOOL_SEO[id])
    .filter(Boolean);

  return (
    <section className="mx-auto w-full max-w-3xl px-4 pb-16 pt-4 font-sans text-neutral-700 dark:text-neutral-300">
      <JsonLd data={toolJsonLd(toolId)} />
      <p className="text-sm leading-relaxed">{tool.lead}</p>

      <h2 className="mt-8 text-lg font-semibold text-neutral-900 dark:text-neutral-50">
        How to {tool.title.toLowerCase()}
      </h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-relaxed">
        {tool.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>

      <h2 className="mt-8 text-lg font-semibold text-neutral-900 dark:text-neutral-50">
        {tool.title} FAQ
      </h2>
      <dl className="mt-3 space-y-4">
        {tool.faqs.map((faq) => (
          <div key={faq.question}>
            <dt className="text-sm font-medium text-neutral-900 dark:text-neutral-50">
              {faq.question}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed">{faq.answer}</dd>
          </div>
        ))}
      </dl>

      {related.length > 0 && (
        <>
          <h2 className="mt-8 text-lg font-semibold text-neutral-900 dark:text-neutral-50">
            Related tools
          </h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {related.map((item) => (
              <li key={item.id}>
                <Link
                  href={item.path}
                  className="inline-flex rounded-full border border-neutral-200 bg-white px-3 py-1 text-sm text-neutral-800 hover:border-blue-400 dark:border-neutral-800 dark:bg-neutral-950 dark:text-neutral-200"
                >
                  {item.title}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
