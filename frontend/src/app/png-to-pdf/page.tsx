import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PNG to PDF",
  description: "Convert PNG images to PDF in seconds.",
};

export default function PngToPdfPage() {
  return (
    <ConverterFlow
      toolId="png-to-pdf"
      title="PNG to PDF"
      description="Convert a PNG image to PDF"
      acceptedExtensions={[".png"]}
      unsupportedMessage="Unsupported file type. Please choose a PNG file."
    />
  );
}
