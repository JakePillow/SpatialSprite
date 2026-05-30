import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type Variant = "success" | "warn" | "danger" | "neutral";

const styles: Record<Variant, string> = {
  success: "bg-success/20 text-success border-success/40",
  warn: "bg-warning/20 text-warning border-warning/40",
  danger: "bg-destructive/20 text-destructive border-destructive/40",
  neutral: "bg-secondary text-muted-foreground border-border",
};

export function Badge({
  children,
  variant = "neutral",
  className,
}: {
  children: ReactNode;
  variant?: Variant;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        styles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}