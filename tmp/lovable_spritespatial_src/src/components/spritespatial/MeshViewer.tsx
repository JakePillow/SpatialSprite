import { useState } from "react";
import { Panel } from "./Panel";
import { cn } from "@/lib/utils";

type View = "front" | "side" | "back";

function MeshWireframe({ wireframe, view }: { wireframe: boolean; view: View }) {
  const stroke = wireframe ? "oklch(0.68 0.17 250)" : "oklch(0.55 0.05 260)";
  const fill = wireframe ? "transparent" : "oklch(0.32 0.05 260)";
  const rotate = view === "front" ? 0 : view === "side" ? 35 : -25;

  return (
    <svg
      viewBox="-100 -110 200 220"
      className="relative h-[75%] max-h-[440px] w-auto drop-shadow-[0_0_24px_oklch(0.68_0.17_250/0.25)]"
      style={{ transform: `perspective(600px) rotateY(${rotate}deg)` }}
    >
      <g fill={fill} stroke={stroke} strokeWidth={0.7} strokeLinejoin="round">
        <circle cx={0} cy={-65} r={22} />
        <ellipse cx={0} cy={-65} rx={22} ry={6} />
        <polygon points="-28,-40 28,-40 22,30 -22,30" />
        <polygon points="-28,-38 -44,-30 -38,18 -24,12" />
        <polygon points="28,-38 44,-30 38,18 24,12" />
        <polygon points="-20,30 -4,30 -6,82 -18,82" />
        <polygon points="4,30 20,30 18,82 6,82" />
        <line x1={-28} y1={-40} x2={28} y2={-40} />
        <line x1={-26} y1={-5} x2={26} y2={-5} />
        <line x1={0} y1={-40} x2={0} y2={30} />
        <line x1={-22} y1={30} x2={22} y2={30} />
      </g>
    </svg>
  );
}

export function MeshViewer() {
  const [wireframe, setWireframe] = useState(true);
  const [view, setView] = useState<View>("front");

  return (
    <Panel
      title="Mesh Preview"
      actions={
        <>
          <button
            type="button"
            onClick={() => setWireframe((w) => !w)}
            className={cn(
              "rounded px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors",
              wireframe
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground",
            )}
          >
            Wireframe
          </button>
          <div className="ml-2 flex items-center gap-0.5 rounded bg-secondary p-0.5">
            {(["front", "side", "back"] as View[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={cn(
                  "rounded px-2 py-0.5 text-[10px] uppercase tracking-wide",
                  view === v
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v}
              </button>
            ))}
          </div>
        </>
      }
      bodyClassName="flex"
    >
      <div className="relative flex flex-1 items-center justify-center bg-[oklch(0.12_0.01_260)]">
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "linear-gradient(oklch(0.22 0.01 260) 1px, transparent 1px), linear-gradient(90deg, oklch(0.22 0.01 260) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,oklch(0.12_0.01_260)_80%)]" />
        <MeshWireframe wireframe={wireframe} view={view} />
        <div className="absolute bottom-2 left-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          view: {view} {wireframe ? "· wire" : "· shaded"}
        </div>
        <div className="absolute right-3 top-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          mesh.preview
        </div>
      </div>
    </Panel>
  );
}