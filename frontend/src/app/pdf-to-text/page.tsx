import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to Text",
  description: "Extract text from a PDF document.",
};

export default function PdfToTextPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-text"
      title="PDF to Text"
      description="Extract the plain text content from a PDF"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
