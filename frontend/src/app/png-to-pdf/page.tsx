import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("png-to-pdf");

export default function PngToPdfPage() {
  return (
    <ToolPageShell toolId="png-to-pdf">
      <ConverterFlow
        toolId="png-to-pdf"
        title="PNG to PDF"
        description="Convert a PNG image to PDF"
        acceptedExtensions={[".png"]}
        unsupportedMessage="Unsupported file type. Please choose a PNG file."
      />
    </ToolPageShell>
  );
}
