import UrlConvertFlow from "@/components/UrlConvertFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("html-to-pdf");

export default function HtmlToPdfPage() {
  return (
    <ToolPageShell toolId="html-to-pdf">
      <UrlConvertFlow />
    </ToolPageShell>
  );
}
