import type { StudioAsset } from "../types/studio";
import { Panel } from "./Panel";

interface SpriteInspectorProps {
  asset: StudioAsset;
}

const views = ["front", "back", "side"] as const;

export function SpriteInspector({ asset }: SpriteInspectorProps) {
  return (
    <Panel
      title="Asset Viewer"
      subtitle={`${asset.id} / authoritative crops`}
    >
      <div className="grid h-full grid-cols-3 gap-3">
        {views.map((view) => (
          <figure key={view} className="studio-panel-chrome flex min-w-0 flex-col border border-studio-border bg-[#120c18]">
            <figcaption className="studio-readout border-b border-studio-border bg-studio-panelAlt px-2 py-1 text-[10px] uppercase tracking-wide text-studio-muted">
              {view}
            </figcaption>
            <div className="studio-grid-bg relative flex flex-1 items-center justify-center p-3">
              <img
                src={asset.sprites[view]}
                alt={`${asset.id} ${view} sprite`}
                className="h-full max-h-36 w-auto max-w-full object-contain [image-rendering:pixelated]"
              />
            </div>
          </figure>
        ))}
      </div>
    </Panel>
  );
}
