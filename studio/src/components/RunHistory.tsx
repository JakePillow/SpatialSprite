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
    <Panel title="Run History" subtitle="Build jobs">
      <div className="space-y-2">
        {runs.map((run) => {
          const selected = run.id === selectedRunId;
          return (
            <button
              key={run.id}
              type="button"
              onClick={() => onSelectRun(run.id)}
              className={`studio-panel-chrome flex w-full items-center gap-3 border px-3 py-2 text-left ${
                selected
                  ? "border-studio-accent bg-studio-accent/15 shadow-[var(--studio-shadow-cyan)]"
                  : "border-studio-border bg-studio-panelAlt hover:border-studio-accent/80"
              }`}
              aria-pressed={selected}
            >
              <History size={15} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-studio-text">{run.id}</span>
                <span className="block truncate text-xs text-studio-muted">
                  {run.asset} / {run.status ?? run.preset}
                </span>
                {run.createdAt ? <span className="studio-readout block truncate text-[10px] text-studio-muted">{run.createdAt}</span> : null}
              </span>
              {run.status ? (
                <span
                  className={`studio-readout border px-1.5 py-0.5 text-[9px] ${
                    run.status === "completed"
                      ? "border-studio-pass/60 bg-studio-pass/10 text-studio-pass"
                      : run.status === "failed"
                        ? "border-studio-fail/60 bg-studio-fail/10 text-studio-fail"
                        : "border-studio-warn/60 bg-studio-warn/10 text-studio-warn"
                  }`}
                >
                  {run.validationPassed === false ? "FAIL" : run.status}
                </span>
              ) : run.hasParamDiffReport ? (
                <span className="studio-readout border border-studio-pass/60 bg-studio-pass/10 px-1.5 py-0.5 text-[9px] text-studio-pass">diff</span>
              ) : null}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
