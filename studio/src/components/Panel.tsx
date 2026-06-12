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
    <section
      className={`studio-panel-chrome flex min-h-0 min-w-0 resize-y flex-col overflow-auto border-2 border-studio-border bg-studio-panel ${className}`}
    >
      <header className="studio-chrome flex min-h-9 min-w-0 items-center justify-between gap-2 border-b-2 border-studio-border px-3">
        <div className="min-w-0">
          <h2 className="studio-wordmark text-xs font-black leading-none text-studio-text">▸ {title}</h2>
          {subtitle ? <p className="studio-readout mt-0.5 text-[10px] text-studio-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className="studio-scrollbar min-h-0 min-w-0 flex-1 overflow-auto p-3">{children}</div>
    </section>
  );
}
