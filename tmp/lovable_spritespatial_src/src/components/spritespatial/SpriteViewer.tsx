import { useState } from "react";
import { Panel } from "./Panel";
import { cn } from "@/lib/utils";

type View = "front" | "back" | "side";
const VIEWS: View[] = ["front", "back", "side"];

interface Props {
  assetId: string;
}

export function SpriteViewer({ assetId }: Props) {
  const [view, setView] = useState<View>("front");
  const [semantic, setSemantic] = useState(false);

  return (
    <Panel
      title="Sprite Viewer"
      actions={
        <div className="flex items-center gap-1 rounded bg-secondary p-0.5 text-[10px]">
          <button
            type="button"
            onClick={() => setSemantic(false)}
            className={cn(
              "rounded px-2 py-0.5 uppercase tracking-wide",
              !semantic ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            Raw
          </button>
          <button
            type="button"
            onClick={() => setSemantic(true)}
            className={cn(
              "rounded px-2 py-0.5 uppercase tracking-wide",
              semantic ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            Semantic
          </button>
        </div>
      }
      bodyClassName="flex flex-col"
    >
      <div className="flex shrink-0 border-b border-border bg-panel-elevated">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn(
              "border-r border-border px-3 py-1.5 text-[11px] uppercase tracking-wide transition-colors",
              view === v
                ? "bg-panel text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {v}
          </button>
        ))}
      </div>
      <div className="flex flex-1 items-center justify-center bg-[oklch(0.14_0.01_260)] p-3">
        <div
          className={cn(
            "relative flex aspect-square w-full max-w-[180px] items-center justify-center overflow-hidden rounded border border-border",
            semantic
              ? "bg-gradient-to-br from-primary/30 via-chart-2/30 to-chart-5/30"
              : "bg-[oklch(0.22_0.01_260)]",
          )}
          style={
            semantic
              ? undefined
              : {
                  backgroundImage:
                    "linear-gradient(45deg, oklch(0.26 0.01 260) 25%, transparent 25%), linear-gradient(-45deg, oklch(0.26 0.01 260) 25%, transparent 25%), linear-gradient(45deg, transparent 75%, oklch(0.26 0.01 260) 75%), linear-gradient(-45deg, transparent 75%, oklch(0.26 0.01 260) 75%)",
                  backgroundSize: "12px 12px",
                  backgroundPosition: "0 0, 0 6px, 6px -6px, -6px 0",
                }
          }
        >
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            {assetId} · {view}
          </span>
        </div>
      </div>
    </Panel>
  );
}