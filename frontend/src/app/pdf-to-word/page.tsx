import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-word");

export default function PdfToWordPage() {
  return (
    <ToolPageShell toolId="pdf-to-word">
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
    </ToolPageShell>
  );
}
