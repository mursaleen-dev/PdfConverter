import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to PNG",
  description: "Convert PDF pages to PNG images.",
};

export default function PdfToPngPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-png"
      title="PDF to PNG"
      description="Convert each page of a PDF into a PNG image (zipped if multi-page)"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
