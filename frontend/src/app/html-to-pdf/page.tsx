import type { Metadata } from "next";
import UrlConvertFlow from "@/components/UrlConvertFlow";

export const metadata: Metadata = {
  title: "HTML to PDF",
  description: "Convert a webpage to PDF from its URL.",
};

export default function HtmlToPdfPage() {
  return <UrlConvertFlow />;
}
