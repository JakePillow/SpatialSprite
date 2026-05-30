import { Panel } from "./Panel";
import { Badge } from "./Badge";
import type { Validation } from "@/lib/spritespatial-data";

interface Props {
  validation: Validation;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded bg-panel-elevated px-2 py-1.5">
      <span className="truncate font-mono text-[11px] text-muted-foreground">{label}</span>
      {value}
    </div>
  );
}

export function ValidationPanel({ validation }: Props) {
  const v = validation;
  return (
    <Panel title="Validation">
      <div className="space-y-2 p-3 text-xs">
        <Row
          label="validation_passed"
          value={
            <Badge variant={v.validation_passed ? "success" : "danger"}>
              {v.validation_passed ? "PASS" : "FAIL"}
            </Badge>
          }
        />
        <Row
          label="mesh_connected_components"
          value={
            <Badge variant={v.mesh_connected_components === 1 ? "success" : "warn"}>
              {v.mesh_connected_components}
            </Badge>
          }
        />
        <Row
          label="degenerate_faces"
          value={
            <Badge variant={v.degenerate_faces === 0 ? "success" : "danger"}>
              {v.degenerate_faces}
            </Badge>
          }
        />
        <Row
          label="non_manifold_edges"
          value={
            <Badge
              variant={
                v.non_manifold_edges === 0
                  ? "success"
                  : v.non_manifold_edges < 5
                    ? "warn"
                    : "danger"
              }
            >
              {v.non_manifold_edges}
            </Badge>
          }
        />
      </div>
    </Panel>
  );
}