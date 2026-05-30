import { Panel } from "./Panel";
import { MOCK_DIFF } from "@/lib/spritespatial-data";
import { ArrowDown, ArrowUp, MinusCircle } from "lucide-react";

function Section({
  title,
  color,
  children,
}: {
  title: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className={`text-[10px] font-semibold uppercase tracking-wider ${color}`}>
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function DeltaRow({
  name,
  delta,
  good,
}: {
  name: string;
  delta: number;
  good?: boolean;
}) {
  const sign = delta > 0 ? "+" : "";
  const positive = delta > 0;
  const colorClass = good ? "text-success" : "text-destructive";
  return (
    <div className="flex items-center justify-between gap-2 rounded bg-panel-elevated px-2 py-1">
      <span className="truncate font-mono text-[11px] text-foreground">{name}</span>
      <span
        className={`flex items-center gap-1 font-mono text-[11px] font-semibold ${colorClass}`}
      >
        {positive ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
        {sign}
        {delta}
      </span>
    </div>
  );
}

export function DiffSummary() {
  return (
    <Panel title="Diff Summary">
      <div className="space-y-3 p-3 text-xs">
        <Section title="Helpful Deltas" color="text-success">
          {MOCK_DIFF.helpful.map((d) => (
            <DeltaRow key={d.name} name={d.name} delta={d.delta} good />
          ))}
        </Section>
        <Section title="Harmful Deltas" color="text-destructive">
          {MOCK_DIFF.harmful.map((d) => (
            <DeltaRow key={d.name} name={d.name} delta={d.delta} />
          ))}
        </Section>
        <Section title="Skipped Parts" color="text-muted-foreground">
          {MOCK_DIFF.skipped.map((s) => (
            <div
              key={s}
              className="flex items-center gap-2 rounded bg-panel-elevated px-2 py-1 font-mono text-[11px] text-muted-foreground"
            >
              <MinusCircle className="h-3 w-3" />
              {s}
            </div>
          ))}
        </Section>
      </div>
    </Panel>
  );
}