import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("jpg-to-pdf");

export default function JpgToPdfPage() {
  return (
    <ToolPageShell toolId="jpg-to-pdf">
      <ConverterFlow
        toolId="jpg-to-pdf"
        title="JPG to PDF"
        description="Convert a JPG image to PDF"
        acceptedExtensions={[".jpg", ".jpeg"]}
        unsupportedMessage="Unsupported file type. Please choose a JPG or JPEG file."
      />
    </ToolPageShell>
  );
}
