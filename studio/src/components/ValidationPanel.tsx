import type { ValidationData } from "../types/studio";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

interface ValidationPanelProps {
  validation: ValidationData;
}

export function ValidationPanel({ validation }: ValidationPanelProps) {
  return (
    <Panel title="Validation" subtitle="Mock latest run" actions={<StatusBadge status={validation.status} />}>
      <div className="space-y-2">
        {validation.metrics.map((metric) => (
          <div
            key={metric.key}
            className="studio-panel-chrome grid grid-cols-[1fr_auto] items-center gap-3 border border-studio-border bg-studio-panelAlt px-2 py-2 text-xs"
          >
            <span className="truncate font-mono text-studio-muted">{metric.key}</span>
            <div className="flex items-center gap-2">
              <span className="font-mono text-studio-text">{String(metric.value)}</span>
              <StatusBadge status={metric.status} />
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
