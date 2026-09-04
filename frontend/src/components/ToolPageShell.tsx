import type { ReactNode } from "react";
import ToolSeoContent from "@/components/ToolSeoContent";

export default function ToolPageShell({
  toolId,
  children,
}: {
  toolId: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-1 flex-col bg-zinc-50 dark:bg-black">
      {children}
      <ToolSeoContent toolId={toolId} />
    </div>
  );
}
