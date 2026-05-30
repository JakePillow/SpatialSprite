import { Play } from "lucide-react";
import type { PresetOption } from "../types/studio";
import { Panel } from "./Panel";

interface PresetPanelProps {
  presets: PresetOption[];
  selectedPresetId: string;
  intensity: number;
  lastAppliedPreset: string | null;
  isApplying?: boolean;
  onSelectPreset: (presetId: string) => void;
  onIntensityChange: (value: number) => void;
  onApply: () => void;
}

export function PresetPanel({
  presets,
  selectedPresetId,
  intensity,
  lastAppliedPreset,
  isApplying = false,
  onSelectPreset,
  onIntensityChange,
  onApply
}: PresetPanelProps) {
  const selectedPreset = presets.find((preset) => preset.id === selectedPresetId);

  return (
    <Panel title="Preset Controls" subtitle="Local mock actions">
      <div className="space-y-4">
        <label className="block text-xs font-semibold text-studio-muted" htmlFor="preset-select">
          Preset
        </label>
        <select
          id="preset-select"
          value={selectedPresetId}
          onChange={(event) => onSelectPreset(event.target.value)}
          className="studio-readout w-full border border-studio-border bg-studio-panelAlt px-3 py-2 text-xs text-studio-text outline-none focus:border-studio-accent"
        >
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.displayName}
            </option>
          ))}
        </select>

        <p className="min-h-10 text-xs leading-5 text-studio-muted">{selectedPreset?.description}</p>

        <label className="flex items-center justify-between text-xs font-semibold text-studio-muted" htmlFor="intensity">
          <span>Intensity</span>
          <span className="font-mono text-studio-text">{intensity.toFixed(2)}</span>
        </label>
        <input
          id="intensity"
          aria-label="Preset intensity"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={intensity}
          onChange={(event) => onIntensityChange(Number(event.target.value))}
          className="w-full accent-studio-accent"
        />

        <button
          type="button"
          onClick={onApply}
          disabled={isApplying}
          className="studio-readout flex w-full items-center justify-center gap-2 border border-studio-accent bg-studio-accent px-3 py-2 text-xs font-black uppercase text-black shadow-[var(--studio-shadow-cyan)] hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
        >
          <Play size={15} aria-hidden="true" />
          {isApplying ? "Applying..." : "Apply Preset"}
        </button>

        <div className="studio-readout border border-studio-border bg-studio-panelAlt px-3 py-2 text-[10px] text-studio-muted">
          Last applied: <span className="font-mono text-studio-text">{lastAppliedPreset ?? "none"}</span>
        </div>
      </div>
    </Panel>
  );
}
