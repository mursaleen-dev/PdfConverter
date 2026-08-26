import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to PowerPoint",
  description: "Convert PDF pages into layout-preserving PowerPoint slides.",
};

export default function PdfToPowerPointPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-powerpoint"
      title="PDF to PowerPoint"
      description="Convert PDF pages into high-quality PPTX slides while preserving layout"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
