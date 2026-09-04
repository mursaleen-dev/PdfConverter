import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("pdf-to-excel");

export default function PdfToExcelPage() {
  return (
    <ToolPageShell toolId="pdf-to-excel">
      <ConverterFlow
        toolId="pdf-to-excel"
        title="PDF to Excel"
        description="Pull data from your PDF into an editable XLSX spreadsheet"
        acceptedExtensions={[".pdf"]}
        unsupportedMessage="Unsupported file type. Please choose a PDF file."
      />
    </ToolPageShell>
  );
}
