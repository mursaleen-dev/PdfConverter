import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to JPG",
  description: "Convert PDF pages to JPG images.",
};

export default function PdfToJpgPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-jpg"
      title="PDF to JPG"
      description="Convert each page of a PDF into a JPG image (zipped if multi-page)"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
