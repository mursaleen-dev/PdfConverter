import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-text");

export default function PdfToTextPage() {
  return (
    <ToolPageShell toolId="pdf-to-text">
      <ConverterFlow
        toolId="pdf-to-text"
        title="PDF to Text"
        description="Extract the plain text content from a PDF"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
