import { AssetBrowser } from "../components/AssetBrowser";
import { DiffSummary } from "../components/DiffSummary";
import { EmbodimentParametersPanel } from "../components/EmbodimentParametersPanel";
import { MeshViewer } from "../components/MeshViewer";
import { PresetPanel } from "../components/PresetPanel";
import { RunHistory } from "../components/RunHistory";
import { SpriteInspector } from "../components/SpriteInspector";
import { TopStatusBar } from "../components/TopStatusBar";
import { ValidationPanel } from "../components/ValidationPanel";
import { useStudioState } from "../hooks/useStudioState";

export function Studio() {
  const studio = useStudioState();

  return (
    <main className="studio-root grid h-screen grid-rows-[auto_280px_minmax(320px,1fr)_220px_auto] gap-2 overflow-hidden p-2 text-studio-text">
      <TopStatusBar
        mode={studio.mode}
        apiStatusMessage={studio.apiStatusMessage}
        selectedAssetId={studio.selectedAssetId}
        selectedPresetId={studio.selectedPresetId}
        selectedRunId={studio.selectedRunId}
        workflowError={studio.workflowError}
      />

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
            isApplying={studio.isApplyingPreset}
            onSelectPreset={studio.setSelectedPresetId}
            onIntensityChange={studio.setIntensity}
            onApply={studio.applyPreset}
          />
          <EmbodimentParametersPanel params={studio.embodimentParams} onChange={studio.updateParam} />
        </div>
      </section>

      <MeshViewer selectedRunId={studio.selectedRunId} mode={studio.mode} />

      <section className="grid min-h-0 grid-cols-[320px_minmax(420px,1fr)_300px] gap-2">
        <ValidationPanel validation={studio.validation} />
        <DiffSummary diff={studio.diffSummary} />
        <RunHistory runs={studio.runs} selectedRunId={studio.selectedRunId} onSelectRun={studio.selectRun} />
      </section>
      <footer className="studio-chrome studio-readout flex h-7 items-center justify-between overflow-hidden border-2 border-studio-border px-3 text-[10px] uppercase text-studio-muted">
        <span>SpriteSpatial v0.1 local studio shell</span>
        <span>backend: {studio.mode === "LIVE" ? "connected" : "mock fallback"}</span>
      </footer>
    </main>
  );
}
