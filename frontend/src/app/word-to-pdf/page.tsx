import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "Word to PDF",
  description: "Convert Word documents to PDF.",
};

export default function WordToPdfPage() {
  return (
    <ConverterFlow
      toolId="word-to-pdf"
      title="Word to PDF"
      description="Convert a DOC or DOCX document to PDF"
      acceptedExtensions={[".doc", ".docx"]}
      unsupportedMessage="Unsupported file type. Please choose a DOC or DOCX file."
    />
  );
}
