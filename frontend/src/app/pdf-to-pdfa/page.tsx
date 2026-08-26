import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to PDF/A",
  description: "Convert a PDF to the PDF/A archival standard.",
};

export default function PdfToPdfaPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-pdfa"
      title="PDF to PDF/A"
      description="Convert a PDF to PDF/A-2b for long-term archiving"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
