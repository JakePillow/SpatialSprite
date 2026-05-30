import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface PanelProps {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Panel({ title, actions, children, className, bodyClassName }: PanelProps) {
  return (
    <div
      className={cn(
        "y2k-bevel relative flex min-h-0 min-w-0 flex-col border-2 border-border bg-panel",
        className,
      )}
    >
      {(title || actions) && (
        <div className="y2k-chrome flex h-7 shrink-0 items-center justify-between border-b-2 border-border px-2">
          {title && (
            <span className="font-pixel text-[12px] leading-none tracking-wider">
              ▸ {title}
            </span>
          )}
          {actions && <div className="flex items-center gap-1">{actions}</div>}
        </div>
      )}
      <div className={cn("min-h-0 min-w-0 flex-1 overflow-auto", bodyClassName)}>
        {children}
      </div>
    </div>
  );
}