import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("text-to-pdf");

export default function TextToPdfPage() {
  return (
    <ToolPageShell toolId="text-to-pdf">
      <ConverterFlow
        toolId="text-to-pdf"
        title="Text to PDF"
        description="Convert a plain .txt file to PDF"
        acceptedExtensions={[".txt"]}
        unsupportedMessage="Unsupported file type. Please choose a TXT file."
      />
    </ToolPageShell>
  );
}
