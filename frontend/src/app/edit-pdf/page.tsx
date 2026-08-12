import type { Metadata } from "next";
import SejdaEditorLoader from "@/components/SejdaEditor/SejdaEditorLoader";

export const metadata: Metadata = {
  title: "Edit PDF",
  description: "Add text, shapes, images, signatures, and freehand drawings to a PDF.",
};

export default function EditPdfPage() {
  return <SejdaEditorLoader />;
}
