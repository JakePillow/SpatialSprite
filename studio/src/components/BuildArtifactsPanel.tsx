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
  surface_nets_report: "surface_nets_report.json",
  voxel_depth_report: "voxel_depth_report.json",
  manifest: "manifest.json",
  depth_field_report: "depth_field_report.json",
  depth_heatmap: "depth_field.png",
  depth_region_overlay: "region_depth_overlay.png",
  depth_silhouette_pin: "silhouette_pin_mask.png",
  depth_cross_section: "depth_cross_section.png"
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
