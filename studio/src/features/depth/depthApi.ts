import type { BuildJob } from "../../types/studio";

export interface DepthArtifactSet {
  heatmap?: string;
  regions?: string;
  silhouettePin?: string;
  crossSection?: string;
  report?: string;
}

export function depthArtifacts(job?: BuildJob | null): DepthArtifactSet {
  const artifacts = job?.artifacts ?? {};
  return {
    heatmap: artifacts.depth_heatmap,
    regions: artifacts.depth_region_overlay,
    silhouettePin: artifacts.depth_silhouette_pin,
    crossSection: artifacts.depth_cross_section,
    report: artifacts.depth_field_report
  };
}
