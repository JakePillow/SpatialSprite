import type { DiffSummaryData } from "../types/studio";
import { Panel } from "./Panel";

interface DiffSummaryProps {
  diff: DiffSummaryData;
}

export function DiffSummary({ diff }: DiffSummaryProps) {
  return (
    <Panel title="Diff Summary" subtitle="Mock parameter delta">
      <div className="grid h-full grid-cols-3 gap-3 text-xs">
        <DiffColumn title="Helpful Deltas" items={diff.helpful} tone="text-studio-pass" />
        <DiffColumn title="Harmful Deltas" items={diff.harmful} tone="text-studio-warn" />
        <DiffColumn title="Skipped Parts" items={diff.skipped} tone="text-studio-muted" />
      </div>
    </Panel>
  );
}

function DiffColumn({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className="min-w-0 border border-studio-border bg-studio-panelAlt p-2">
      <h3 className="mb-2 font-semibold text-studio-text">{title}</h3>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className={`truncate font-mono ${tone}`}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
