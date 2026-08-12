import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "Excel to PDF",
  description: "Convert Excel spreadsheets to PDF.",
};

export default function ExcelToPdfPage() {
  return (
    <ConverterFlow
      toolId="excel-to-pdf"
      title="Excel to PDF"
      description="Convert an XLS or XLSX spreadsheet to PDF"
      acceptedExtensions={[".xls", ".xlsx"]}
      unsupportedMessage="Unsupported file type. Please choose an XLS or XLSX file."
    />
  );
}
