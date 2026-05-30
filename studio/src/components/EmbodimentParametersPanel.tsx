import type { EmbodimentParameters } from "../types/studio";
import { Panel } from "./Panel";

interface EmbodimentParametersPanelProps {
  params: EmbodimentParameters;
  onChange: (key: keyof EmbodimentParameters, value: number) => void;
}

const fields: Array<{ key: keyof EmbodimentParameters; min: number; max: number; step: number }> = [
  { key: "z_center_offset", min: -1, max: 1, step: 0.05 },
  { key: "thickness_scale", min: 0.2, max: 2, step: 0.05 },
  { key: "front_bias", min: 0, max: 1, step: 0.01 },
  { key: "back_bias", min: 0, max: 1, step: 0.01 },
  { key: "side_width_scale", min: 0.2, max: 2, step: 0.05 },
  { key: "taper_strength", min: 0, max: 1, step: 0.01 }
];

export function EmbodimentParametersPanel({ params, onChange }: EmbodimentParametersPanelProps) {
  return (
    <Panel title="Embodiment Parameters" subtitle="Editable local state">
      <div className="space-y-3">
        {fields.map((field) => (
          <label key={field.key} className="grid grid-cols-[1fr_4.5rem] items-center gap-3 text-xs text-studio-muted">
            <span className="truncate font-mono">{field.key}</span>
            <input
              aria-label={field.key}
              type="number"
              min={field.min}
              max={field.max}
              step={field.step}
              value={params[field.key]}
              onChange={(event) => onChange(field.key, Number(event.target.value))}
              className="w-full border border-studio-border bg-studio-panelAlt px-2 py-1 text-right font-mono text-studio-text outline-none focus:border-studio-accent"
            />
          </label>
        ))}
      </div>
    </Panel>
  );
}
