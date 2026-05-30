import { History } from "lucide-react";
import type { RunHistoryItem } from "../types/studio";
import { Panel } from "./Panel";

interface RunHistoryProps {
  runs: RunHistoryItem[];
  selectedRunId: string;
  onSelectRun: (runId: string) => void;
}

export function RunHistory({ runs, selectedRunId, onSelectRun }: RunHistoryProps) {
  return (
    <Panel title="Run History" subtitle="Mock local runs">
      <div className="space-y-2">
        {runs.map((run) => {
          const selected = run.id === selectedRunId;
          return (
            <button
              key={run.id}
              type="button"
              onClick={() => onSelectRun(run.id)}
              className={`flex w-full items-center gap-3 border px-3 py-2 text-left ${
                selected
                  ? "border-studio-accent bg-studio-accent/15"
                  : "border-studio-border bg-studio-panelAlt hover:border-studio-muted"
              }`}
              aria-pressed={selected}
            >
              <History size={15} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-studio-text">{run.id}</span>
                <span className="block truncate text-xs text-studio-muted">
                  {run.asset} / {run.preset}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
