import SejdaEditorLoader from "@/components/SejdaEditor/SejdaEditorLoader";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("edit-pdf");

export default function EditPdfPage() {
  return (
    <ToolPageShell toolId="edit-pdf">
      <SejdaEditorLoader />
    </ToolPageShell>
  );
}
