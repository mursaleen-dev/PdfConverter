import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "Text to PDF",
  description: "Convert plain text files to PDF.",
};

export default function TextToPdfPage() {
  return (
    <ConverterFlow
      toolId="text-to-pdf"
      title="Text to PDF"
      description="Convert a plain .txt file to PDF"
      acceptedExtensions={[".txt"]}
      unsupportedMessage="Unsupported file type. Please choose a TXT file."
    />
  );
}
