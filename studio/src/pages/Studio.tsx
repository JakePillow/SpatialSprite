import { AssetBrowser } from "../components/AssetBrowser";
import { AssetCreationPanel } from "../components/AssetCreationPanel";
import { BuildArtifactsPanel } from "../components/BuildArtifactsPanel";
import { CandidateGrid } from "../components/CandidateGrid";
import { EmbodimentParametersPanel } from "../components/EmbodimentParametersPanel";
import { MeshViewer } from "../components/MeshViewer";
import { PresetPanel } from "../components/PresetPanel";
import { RunHistory } from "../components/RunHistory";
import { SourceSheetBrowser } from "../components/SourceSheetBrowser";
import { SourceSheetPreview } from "../components/SourceSheetPreview";
import { SpriteInspector } from "../components/SpriteInspector";
import { TopStatusBar } from "../components/TopStatusBar";
import { ValidationPanel } from "../components/ValidationPanel";
import { ViewAssignmentPanel } from "../components/ViewAssignmentPanel";
import { fileUrl } from "../api/sheets";
import { useStudioState } from "../hooks/useStudioState";

export function Studio() {
  const studio = useStudioState();
  const imageUrlForPath = (path?: string | null) =>
    studio.mode === "MOCK" && path && !path.startsWith("/") ? "/placeholders/front.svg" : fileUrl(path);

  return (
    <main className="studio-root grid min-h-screen grid-rows-[auto_minmax(260px,35vh)_minmax(360px,48vh)_minmax(240px,32vh)_minmax(360px,58vh)_minmax(220px,32vh)_auto] gap-2 overflow-x-hidden overflow-y-auto p-2 text-studio-text">
      <TopStatusBar
        mode={studio.mode}
        apiStatusMessage={studio.apiStatusMessage}
        selectedAssetId={studio.selectedAssetId}
        selectedPresetId={studio.selectedPresetId}
        selectedRunId={studio.selectedBuildJob?.job_id}
        workflowError={studio.workflowError}
        onReconnect={studio.reconnectApi}
      />

      <section className="grid min-h-64 min-w-0 resize-y grid-cols-[260px_minmax(360px,1fr)_360px] gap-2 overflow-auto">
        <AssetBrowser
          assets={studio.assets}
          selectedAssetId={studio.selectedAssetId}
          onSelectAsset={studio.selectAsset}
          onNewAsset={studio.startNewAsset}
          onRenameAsset={studio.renameAsset}
          onDeleteAsset={studio.deleteAsset}
          onMoveAsset={studio.moveAsset}
        />
        <SpriteInspector asset={studio.selectedAsset} />
        <div className="grid min-h-0 min-w-0 grid-rows-[1fr_1fr] gap-2">
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

      <section className="grid min-h-80 min-w-0 resize-y grid-cols-[260px_minmax(420px,1fr)_330px] gap-2 overflow-auto">
        <SourceSheetBrowser
          sheets={studio.rawSheets}
          selectedSheetPath={studio.selectedSheetPath}
          isUploading={studio.isUploadingSheet}
          uploadDisabled={studio.mode !== "LIVE"}
          uploadDisabledLabel="API Required"
          uploadError={studio.sheetUploadError}
          imageUrlForSheet={(sheet) => imageUrlForPath(sheet.path)}
          onSelectSheet={studio.selectSheet}
          onUploadSheet={studio.uploadSheet}
        />
        <SourceSheetPreview
          sheet={studio.selectedSheet}
          sheetImageUrl={imageUrlForPath(studio.selectedSheet?.path)}
          candidateRun={studio.candidateRun}
          contactSheetUrl={imageUrlForPath(studio.candidateRun?.candidate_contact_sheet)}
          isExtracting={studio.isExtractingCandidates}
          onExtract={studio.extractCandidates}
        />
        <div className="grid min-h-0 min-w-0 grid-rows-[1fr_1fr] gap-2">
          <ViewAssignmentPanel
            candidates={studio.candidateRun?.candidates ?? []}
            selectedCandidate={studio.selectedCandidate}
            assignments={studio.viewAssignments}
            activeViewRole={studio.activeViewRole}
            imageUrlForCandidate={(candidate) => imageUrlForPath(candidate.path)}
            onActiveViewChange={studio.setActiveViewRole}
            onAssign={studio.assignCandidateToView}
            onClear={studio.clearViewAssignment}
          />
          <AssetCreationPanel
            assetId={studio.newAssetId}
            candidateRun={studio.candidateRun}
            assignments={studio.viewAssignments}
            selectionMode={studio.viewSelectionMode}
            warnings={studio.viewSelectionWarnings}
            isCreating={studio.isCreatingAsset}
            result={studio.assetCreationResult}
            error={studio.assetCreationError}
            isBuilding={studio.isStartingBuild}
            onAssetIdChange={studio.setNewAssetId}
            onGenerateAssetId={studio.generateNewAssetId}
            onSelectionModeChange={studio.setViewSelectionMode}
            onCreate={studio.createAssetFromCandidates}
            onCreateAndBuild={studio.createAssetAndBuild}
          />
        </div>
      </section>

      <CandidateGrid
        candidates={studio.candidateRun?.candidates ?? []}
        selectedCandidateId={studio.selectedCandidateId}
        assignments={studio.viewAssignments}
        activeViewRole={studio.activeViewRole}
        imageUrlForCandidate={(candidate) => imageUrlForPath(candidate.path)}
        onSelectCandidate={studio.selectCandidateForActiveView}
      />

      <MeshViewer job={studio.selectedBuildJob} mode={studio.mode} />

      <section className="grid min-h-0 min-w-0 grid-cols-[320px_minmax(420px,1fr)_300px] gap-2">
        <ValidationPanel validation={studio.validation} />
        <BuildArtifactsPanel job={studio.selectedBuildJob} />
        <RunHistory runs={studio.buildRunItems} selectedRunId={studio.selectedBuildJobId} onSelectRun={studio.selectBuildJob} />
      </section>
      <footer className="studio-chrome studio-readout flex h-7 items-center justify-between overflow-hidden border-2 border-studio-border px-3 text-[10px] uppercase text-studio-muted">
        <span>SpriteSpatial v0.1 local studio shell</span>
        <span>backend: {studio.mode === "LIVE" ? "connected" : "mock fallback"}</span>
      </footer>
    </main>
  );
}
