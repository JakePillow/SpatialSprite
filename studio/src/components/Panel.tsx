import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, subtitle, actions, children, className = "" }: PanelProps) {
  return (
    <section className={`flex min-h-0 flex-col border border-studio-border bg-studio-panel ${className}`}>
      <header className="flex min-h-12 items-center justify-between border-b border-studio-border px-3">
        <div>
          <h2 className="text-sm font-semibold text-studio-text">{title}</h2>
          {subtitle ? <p className="text-xs text-studio-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      <div className="studio-scrollbar min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </section>
  );
}
