import MergeFlow from "@/components/MergeFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("merge-pdf");

export default function MergePdfPage() {
  return (
    <ToolPageShell toolId="merge-pdf">
      <MergeFlow />
    </ToolPageShell>
  );
}
