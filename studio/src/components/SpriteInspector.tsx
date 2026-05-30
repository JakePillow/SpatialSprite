import type { SpriteMode, StudioAsset } from "../types/studio";
import { Panel } from "./Panel";

interface SpriteInspectorProps {
  asset: StudioAsset;
  mode: SpriteMode;
  onModeChange: (mode: SpriteMode) => void;
}

const views = ["front", "back", "side"] as const;

export function SpriteInspector({ asset, mode, onModeChange }: SpriteInspectorProps) {
  return (
    <Panel
      title="Sprite View"
      subtitle={asset.id}
      actions={
        <div className="flex border border-studio-border bg-studio-panelAlt" aria-label="Sprite display mode">
          {(["raw", "semantic"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onModeChange(option)}
              className={`px-2 py-1 text-xs ${
                mode === option ? "bg-studio-accent text-white" : "text-studio-muted hover:text-studio-text"
              }`}
              aria-pressed={mode === option}
            >
              {option === "raw" ? "Raw" : "Semantic Overlay"}
            </button>
          ))}
        </div>
      }
    >
      <div className="grid h-full grid-cols-3 gap-3">
        {views.map((view) => (
          <figure key={view} className="flex min-w-0 flex-col border border-studio-border bg-[#0f1318]">
            <figcaption className="border-b border-studio-border px-2 py-1 text-xs uppercase tracking-wide text-studio-muted">
              {view}
            </figcaption>
            <div className="relative flex flex-1 items-center justify-center p-3">
              <img
                src={asset.sprites[view]}
                alt={`${asset.id} ${view} sprite`}
                className="h-full max-h-36 w-auto max-w-full object-contain [image-rendering:pixelated]"
              />
              {mode === "semantic" ? (
                <div
                  className="pointer-events-none absolute inset-3 border border-studio-accent/70 bg-studio-accent/10 mix-blend-screen"
                  aria-hidden="true"
                />
              ) : null}
            </div>
          </figure>
        ))}
      </div>
    </Panel>
  );
}
