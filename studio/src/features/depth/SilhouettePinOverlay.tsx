import { DepthHeatmap } from "./DepthHeatmap";

export function SilhouettePinOverlay({ src }: { src?: string }) {
  return <DepthHeatmap title="Silhouette pin" src={src} />;
}
