import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-jpg");

export default function PdfToJpgPage() {
  return (
    <ToolPageShell toolId="pdf-to-jpg">
      <ConverterFlow
        toolId="pdf-to-jpg"
        title="PDF to JPG"
        description="Convert each page of a PDF into a JPG image (zipped if multi-page)"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
