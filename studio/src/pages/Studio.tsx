import { AssetBrowser } from "../components/AssetBrowser";
import { DiffSummary } from "../components/DiffSummary";
import { EmbodimentParametersPanel } from "../components/EmbodimentParametersPanel";
import { MeshViewer } from "../components/MeshViewer";
import { PresetPanel } from "../components/PresetPanel";
import { RunHistory } from "../components/RunHistory";
import { SpriteInspector } from "../components/SpriteInspector";
import { ValidationPanel } from "../components/ValidationPanel";
import { useStudioState } from "../hooks/useStudioState";

export function Studio() {
  const studio = useStudioState();

  return (
    <main className="grid h-screen grid-rows-[280px_minmax(320px,1fr)_220px] gap-2 overflow-hidden bg-studio-bg p-2 text-studio-text">
      <section className="grid min-h-0 grid-cols-[260px_minmax(360px,1fr)_360px] gap-2">
        <AssetBrowser
          assets={studio.assets}
          selectedAssetId={studio.selectedAssetId}
          onSelectAsset={studio.setSelectedAssetId}
        />
        <SpriteInspector asset={studio.selectedAsset} mode={studio.spriteMode} onModeChange={studio.setSpriteMode} />
        <div className="grid min-h-0 grid-rows-[1fr_1fr] gap-2">
          <PresetPanel
            presets={studio.presets}
            selectedPresetId={studio.selectedPresetId}
            intensity={studio.intensity}
            lastAppliedPreset={studio.lastAppliedPreset}
            onSelectPreset={studio.setSelectedPresetId}
            onIntensityChange={studio.setIntensity}
            onApply={studio.applyPreset}
          />
          <EmbodimentParametersPanel params={studio.embodimentParams} onChange={studio.updateParam} />
        </div>
      </section>

      <MeshViewer />

      <section className="grid min-h-0 grid-cols-[320px_minmax(420px,1fr)_300px] gap-2">
        <ValidationPanel validation={studio.validation} />
        <DiffSummary diff={studio.diffSummary} />
        <RunHistory runs={studio.runs} selectedRunId={studio.selectedRunId} onSelectRun={studio.selectRun} />
      </section>
    </main>
  );
}
