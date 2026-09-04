import type { Metadata } from "next";
import { SITE_NAME, SITE_TAGLINE, getSiteUrl } from "@/lib/site";
import { HOME_SEO, TOOL_SEO, getToolSeo } from "@/lib/seo-content";
import { tools } from "@/lib/tools";

export function absoluteUrl(path = "/"): string {
  const base = getSiteUrl();
  if (path === "/") return base;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export function rootMetadata(): Metadata {
  const url = getSiteUrl();
  return {
    metadataBase: new URL(url),
    title: {
      default: `${HOME_SEO.metaTitle} | ${SITE_NAME}`,
      template: `%s | ${SITE_NAME}`,
    },
    description: HOME_SEO.metaDescription,
    applicationName: SITE_NAME,
    authors: [{ name: SITE_NAME }],
    robots: { index: true, follow: true },
    openGraph: {
      type: "website",
      locale: "en_US",
      siteName: SITE_NAME,
      title: HOME_SEO.metaTitle,
      description: HOME_SEO.metaDescription,
      url,
    },
    twitter: {
      card: "summary_large_image",
      title: HOME_SEO.metaTitle,
      description: HOME_SEO.metaDescription,
    },
    alternates: { canonical: "/" },
  };
}

export function toolPageMetadata(id: string): Metadata {
  const tool = getToolSeo(id);
  return {
    title: tool.metaTitle,
    description: tool.metaDescription,
    alternates: { canonical: tool.path },
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      title: tool.metaTitle,
      description: tool.metaDescription,
      url: tool.path,
    },
    twitter: {
      card: "summary_large_image",
      title: tool.metaTitle,
      description: tool.metaDescription,
    },
  };
}

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: getSiteUrl(),
    description: SITE_TAGLINE,
  };
}

export function softwareJsonLd() {
  const url = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE_NAME,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    url,
    description: HOME_SEO.metaDescription,
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
    },
    featureList: tools.filter((tool) => tool.implemented).map((tool) => tool.title),
  };
}

export function toolJsonLd(id: string) {
  const tool = getToolSeo(id);
  const url = absoluteUrl(tool.path);
  return [
    {
      "@context": "https://schema.org",
      "@type": "WebApplication",
      name: `${tool.title} | ${SITE_NAME}`,
      url,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      description: tool.metaDescription,
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: tool.faqs.map((faq) => ({
        "@type": "Question",
        name: faq.question,
        acceptedAnswer: {
          "@type": "Answer",
          text: faq.answer,
        },
      })),
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          name: "Home",
          item: getSiteUrl(),
        },
        {
          "@type": "ListItem",
          position: 2,
          name: tool.title,
          item: url,
        },
      ],
    },
  ];
}

export function allToolPaths(): string[] {
  return Object.values(TOOL_SEO).map((tool) => tool.path);
}
