import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to Word",
  description: "Convert PDF files into editable DOC and DOCX documents.",
};

export default function PdfToWordPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-word"
      title="PDF to Word"
      description="Convert your PDF files into easy to edit DOC and DOCX documents."
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
      conversionModes={[
        {
          value: "keep-layout",
          label: "Keep layout",
          description: "Matches the PDF visually. Content is saved as page images and is not directly editable.",
        },
        {
          value: "editable",
          label: "Editable text",
          description: "Creates editable paragraphs, tables, and images. Complex layouts may shift.",
        },
      ]}
    />
  );
}
