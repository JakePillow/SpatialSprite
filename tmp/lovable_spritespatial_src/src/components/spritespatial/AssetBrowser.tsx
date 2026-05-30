import { Box } from "lucide-react";
import { cn } from "@/lib/utils";
import { Panel } from "./Panel";
import type { Asset } from "@/lib/spritespatial-data";

interface Props {
  assets: Asset[];
  selectedId: string;
  onSelect: (id: string) => void;
}

export function AssetBrowser({ assets, selectedId, onSelect }: Props) {
  return (
    <Panel title="Asset Browser">
      <ul className="p-1">
        {assets.map((a) => {
          const active = a.id === selectedId;
          return (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => onSelect(a.id)}
                className={cn(
                  "group flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-foreground hover:bg-accent/60",
                )}
              >
                <Box className="h-3.5 w-3.5 text-primary" />
                <span className="flex-1 truncate font-medium">{a.id}</span>
                <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {a.coverage}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}