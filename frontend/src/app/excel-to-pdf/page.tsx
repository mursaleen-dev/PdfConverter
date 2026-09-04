import ConverterFlow from "@/components/ConverterFlow";
import ToolPageShell from "@/components/ToolPageShell";
import { toolPageMetadata } from "@/lib/seo";

export const metadata = toolPageMetadata("excel-to-pdf");

export default function ExcelToPdfPage() {
  return (
    <ToolPageShell toolId="excel-to-pdf">
      <ConverterFlow
        toolId="excel-to-pdf"
        title="Excel to PDF"
        description="Convert an XLS or XLSX spreadsheet to PDF"
        acceptedExtensions={[".xls", ".xlsx"]}
        unsupportedMessage="Unsupported file type. Please choose an XLS or XLSX file."
      />
    </ToolPageShell>
  );
}
