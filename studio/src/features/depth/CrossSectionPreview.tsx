import { DepthHeatmap } from "./DepthHeatmap";

export function CrossSectionPreview({ src }: { src?: string }) {
  return <DepthHeatmap title="Side cross-section" src={src} />;
}
