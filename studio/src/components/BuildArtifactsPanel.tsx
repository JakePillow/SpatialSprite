import type { BuildJob } from "../types/studio";
import { fileUrl } from "../api/sheets";
import { Panel } from "./Panel";

interface BuildArtifactsPanelProps {
  job?: BuildJob | null;
}

const artifactLabels: Record<string, string> = {
  validation_report: "validation_report.json",
  topological_model: "topological_model.json",
  mesh: "mesh.json",
  mesh_topology_cleaned: "mesh_topology_cleaned.json",
  manifest: "manifest.json"
};

export function BuildArtifactsPanel({ job }: BuildArtifactsPanelProps) {
  const artifacts = job?.artifacts ?? {};
  const entries = Object.entries(artifactLabels).filter(([key]) => artifacts[key]);
  return (
    <Panel title="Build Artifacts" subtitle={job?.job_id ?? "no build selected"}>
      {entries.length === 0 ? (
        <p className="studio-readout text-[11px] text-studio-muted">No build artifacts available yet.</p>
      ) : (
        <div className="space-y-2">
          {entries.map(([key, label]) => (
            <a
              key={key}
              href={fileUrl(artifacts[key])}
              target="_blank"
              rel="noreferrer"
              className="studio-readout block border border-studio-border bg-studio-panelAlt px-2 py-2 text-[11px] text-studio-cyan hover:border-studio-cyan hover:text-studio-text"
            >
              {label}
            </a>
          ))}
        </div>
      )}
    </Panel>
  );
}
