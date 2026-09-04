import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-pdfa");

export default function PdfToPdfaPage() {
  return (
    <ToolPageShell toolId="pdf-to-pdfa">
      <ConverterFlow
        toolId="pdf-to-pdfa"
        title="PDF to PDF/A"
        description="Convert a PDF to PDF/A-2b for long-term archiving"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
