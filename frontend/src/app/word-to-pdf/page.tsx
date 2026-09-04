import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("word-to-pdf");

export default function WordToPdfPage() {
  return (
    <ToolPageShell toolId="word-to-pdf">
      <ConverterFlow
        toolId="word-to-pdf"
        title="Word to PDF"
        description="Convert a DOC or DOCX document to PDF"
        acceptedExtensions={[".doc", ".docx"]}
        unsupportedMessage="Unsupported file type. Please choose a DOC or DOCX file."
      />
    </ToolPageShell>
  );
}
