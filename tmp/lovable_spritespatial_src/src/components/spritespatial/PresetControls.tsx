import { useState } from "react";
import { Panel } from "./Panel";
import {
  PRESETS,
  DEFAULT_EMBODIMENT,
  type EmbodimentParams,
  type Preset,
} from "@/lib/spritespatial-data";

function Label({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label
      className={`text-[11px] uppercase tracking-wide text-muted-foreground ${className}`}
    >
      {children}
    </label>
  );
}

export function PresetControls() {
  const [preset, setPreset] = useState<Preset>(PRESETS[0]);
  const [intensity, setIntensity] = useState(0.5);
  const [params, setParams] = useState<EmbodimentParams>(DEFAULT_EMBODIMENT);

  const update = (k: keyof EmbodimentParams, v: number) =>
    setParams((p) => ({ ...p, [k]: v }));

  return (
    <Panel title="Preset & Embodiment">
      <div className="space-y-4 p-3">
        <div className="space-y-1.5">
          <Label>Preset</Label>
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value as Preset)}
            className="w-full rounded border border-border bg-input px-2 py-1.5 text-xs text-foreground focus:border-ring focus:outline-none"
          >
            {PRESETS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Intensity</Label>
            <span className="font-mono text-[11px] text-primary">
              {intensity.toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={intensity}
            onChange={(e) => setIntensity(parseFloat(e.target.value))}
            className="w-full accent-primary"
          />
        </div>

        <button
          type="button"
          className="w-full rounded bg-primary px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-primary-foreground transition-opacity hover:opacity-90"
        >
          Apply Preset
        </button>

        <div className="space-y-2 border-t border-border pt-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Embodiment
          </div>
          {(Object.keys(params) as Array<keyof EmbodimentParams>).map((k) => (
            <div key={k} className="flex items-center gap-2">
              <Label className="flex-1 truncate">{k}</Label>
              <input
                type="number"
                step={0.05}
                value={params[k]}
                onChange={(e) => update(k, parseFloat(e.target.value) || 0)}
                className="w-20 rounded border border-border bg-input px-1.5 py-1 text-right font-mono text-[11px] text-foreground focus:border-ring focus:outline-none"
              />
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}