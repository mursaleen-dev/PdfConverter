import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-powerpoint");

export default function PdfToPowerPointPage() {
  return (
    <ToolPageShell toolId="pdf-to-powerpoint">
      <ConverterFlow
        toolId="pdf-to-powerpoint"
        title="PDF to PowerPoint"
        description="Convert PDF pages into high-quality PPTX slides while preserving layout"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
