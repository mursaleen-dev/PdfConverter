import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "JPG to PDF",
  description: "Convert JPG images to PDF in seconds.",
};

export default function JpgToPdfPage() {
  return (
    <ConverterFlow
      toolId="jpg-to-pdf"
      title="JPG to PDF"
      description="Convert a JPG image to PDF"
      acceptedExtensions={[".jpg", ".jpeg"]}
      unsupportedMessage="Unsupported file type. Please choose a JPG or JPEG file."
    />
  );
}
