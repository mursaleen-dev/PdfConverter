import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("powerpoint-to-pdf");

export default function PowerpointToPdfPage() {
  return (
    <ToolPageShell toolId="powerpoint-to-pdf">
      <ConverterFlow
        toolId="powerpoint-to-pdf"
        title="PowerPoint to PDF"
        description="Convert a PPT or PPTX slideshow to PDF"
        acceptedExtensions={[".ppt", ".pptx"]}
        unsupportedMessage="Unsupported file type. Please choose a PPT or PPTX file."
      />
    </ToolPageShell>
  );
}
