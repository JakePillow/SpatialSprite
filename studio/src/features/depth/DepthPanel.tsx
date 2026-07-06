import { fileUrl } from "../../api/sheets";
import { Panel } from "../../components/Panel";
import type { BuildJob } from "../../types/studio";
import { CrossSectionPreview } from "./CrossSectionPreview";
import { DepthHeatmap } from "./DepthHeatmap";
import { SilhouettePinOverlay } from "./SilhouettePinOverlay";
import { depthArtifacts } from "./depthApi";

export function DepthPanel({ job }: { job?: BuildJob | null }) {
  const artifacts = depthArtifacts(job);
  const url = (path?: string) => (path ? fileUrl(path) : undefined);
  return (
    <Panel title="Depth Studio" subtitle={job ? "pre-mesh diagnostics" : "no build selected"}>
      <div className="grid grid-cols-2 gap-2">
        <DepthHeatmap title="Pinned Z-field" src={url(artifacts.heatmap)} />
        <DepthHeatmap title="Semantic regions" src={url(artifacts.regions)} />
        <SilhouettePinOverlay src={url(artifacts.silhouettePin)} />
        <CrossSectionPreview src={url(artifacts.crossSection)} />
      </div>
      {artifacts.report && (
        <a
          href={url(artifacts.report)}
          target="_blank"
          rel="noreferrer"
          className="studio-readout mt-2 block border border-studio-border px-2 py-1 text-[10px] text-studio-cyan"
        >
          Open structured depth report
        </a>
      )}
    </Panel>
  );
}
