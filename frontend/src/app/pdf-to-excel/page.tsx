import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PDF to Excel",
  description: "Extract PDF tables into an editable Excel spreadsheet.",
};

export default function PdfToExcelPage() {
  return (
    <ConverterFlow
      toolId="pdf-to-excel"
      title="PDF to Excel"
      description="Pull data from your PDF into an editable XLSX spreadsheet"
      acceptedExtensions={[".pdf"]}
      unsupportedMessage="Unsupported file type. Please choose a PDF file."
    />
  );
}
