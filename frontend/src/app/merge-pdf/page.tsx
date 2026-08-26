import type { Metadata } from "next";
import MergeFlow from "@/components/MergeFlow";

export const metadata: Metadata = {
  title: "Merge PDF",
  description: "Combine multiple PDF files into one document.",
};

export default function MergePdfPage() {
  return <MergeFlow />;
}
