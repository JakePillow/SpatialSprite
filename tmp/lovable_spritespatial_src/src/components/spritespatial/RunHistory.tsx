import { Panel } from "./Panel";
import { MOCK_RUNS } from "@/lib/spritespatial-data";
import { Play } from "lucide-react";

export function RunHistory() {
  return (
    <Panel title="Run History">
      <ul className="divide-y divide-border">
        {MOCK_RUNS.map((r) => (
          <li
            key={r.id}
            className="flex items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-accent/40"
          >
            <Play className="h-3 w-3 text-primary" />
            <span className="font-mono text-[11px] text-foreground">{r.id}</span>
            <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {r.preset}
            </span>
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {r.asset}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}