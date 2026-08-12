import type { Metadata } from "next";
import ConverterFlow from "@/components/ConverterFlow";

export const metadata: Metadata = {
  title: "PowerPoint to PDF",
  description: "Convert PowerPoint slideshows to PDF.",
};

export default function PowerpointToPdfPage() {
  return (
    <ConverterFlow
      toolId="powerpoint-to-pdf"
      title="PowerPoint to PDF"
      description="Convert a PPT or PPTX slideshow to PDF"
      acceptedExtensions={[".ppt", ".pptx"]}
      unsupportedMessage="Unsupported file type. Please choose a PPT or PPTX file."
    />
  );
}
