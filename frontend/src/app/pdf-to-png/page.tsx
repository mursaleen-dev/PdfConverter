import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-png");

export default function PdfToPngPage() {
  return (
    <ToolPageShell toolId="pdf-to-png">
      <ConverterFlow
        toolId="pdf-to-png"
        title="PDF to PNG"
        description="Convert each page of a PDF into a PNG image (zipped if multi-page)"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
