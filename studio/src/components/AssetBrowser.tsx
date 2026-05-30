import { Box } from "lucide-react";
import type { StudioAsset } from "../types/studio";
import { Panel } from "./Panel";

interface AssetBrowserProps {
  assets: StudioAsset[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
}

export function AssetBrowser({ assets, selectedAssetId, onSelectAsset }: AssetBrowserProps) {
  return (
    <Panel title="Asset Browser" subtitle="Mock project assets">
      <div className="space-y-2" role="list" aria-label="Asset list">
        {assets.map((asset) => {
          const selected = asset.id === selectedAssetId;
          return (
            <button
              key={asset.id}
              type="button"
              onClick={() => onSelectAsset(asset.id)}
              className={`studio-panel-chrome flex w-full items-center gap-3 border px-3 py-2 text-left transition ${
                selected
                  ? "border-studio-accent bg-studio-accent/15 text-white shadow-[var(--studio-shadow-cyan)]"
                  : "border-studio-border bg-studio-panelAlt text-studio-text hover:border-studio-accent/80"
              }`}
              aria-pressed={selected}
            >
              <Box size={16} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{asset.id}</span>
                <span className="studio-readout block truncate text-[10px] uppercase text-studio-muted">{asset.coverage}</span>
              </span>
              {asset.availableSprites ? (
                <span className="studio-readout border border-studio-border bg-studio-panel px-1.5 py-0.5 text-[9px] text-studio-muted">
                  {Object.values(asset.availableSprites).filter(Boolean).length}v
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
