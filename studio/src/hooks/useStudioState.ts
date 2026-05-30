import { useMemo, useState } from "react";
import { mockStudioApi } from "../api/mockStudioApi";
import { defaultEmbodimentParams } from "../mock/studioMock";
import type { EmbodimentParameters, SpriteMode } from "../types/studio";

export function useStudioState() {
  const assets = useMemo(() => mockStudioApi.listAssets(), []);
  const presets = useMemo(() => mockStudioApi.listPresets(), []);
  const runs = useMemo(() => mockStudioApi.listRuns(), []);
  const [selectedAssetId, setSelectedAssetId] = useState(assets[1]?.id ?? assets[0]?.id ?? "");
  const [selectedPresetId, setSelectedPresetId] = useState(presets[0]?.id ?? "");
  const [selectedRunId, setSelectedRunId] = useState(runs[0]?.id ?? "");
  const [spriteMode, setSpriteMode] = useState<SpriteMode>("raw");
  const [intensity, setIntensity] = useState(0.75);
  const [embodimentParams, setEmbodimentParams] = useState<EmbodimentParameters>(defaultEmbodimentParams);
  const [lastAppliedPreset, setLastAppliedPreset] = useState<string | null>(null);

  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) ?? assets[0];
  const selectedPreset = presets.find((preset) => preset.id === selectedPresetId) ?? presets[0];
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? runs[0];

  const updateParam = (key: keyof EmbodimentParameters, value: number) => {
    setEmbodimentParams((current) => ({
      ...current,
      [key]: value
    }));
  };

  const applyPreset = () => {
    setLastAppliedPreset(`${selectedPresetId}@${intensity.toFixed(2)}`);
  };

  const selectRun = (runId: string) => {
    const run = runs.find((item) => item.id === runId);
    if (!run) {
      return;
    }
    setSelectedRunId(runId);
    setSelectedAssetId(run.asset);
    setSelectedPresetId(run.preset);
    setLastAppliedPreset(`${run.preset}@history`);
  };

  return {
    assets,
    presets,
    runs,
    selectedAsset,
    selectedAssetId,
    setSelectedAssetId,
    selectedPreset,
    selectedPresetId,
    setSelectedPresetId,
    selectedRun,
    selectedRunId,
    selectRun,
    spriteMode,
    setSpriteMode,
    intensity,
    setIntensity,
    embodimentParams,
    updateParam,
    applyPreset,
    lastAppliedPreset,
    diffSummary: mockStudioApi.getDiffSummary(),
    validation: mockStudioApi.getValidation()
  };
}
