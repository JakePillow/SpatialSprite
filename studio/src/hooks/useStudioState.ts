import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiAssetDetail, ApiAssetSummary } from "../api/assets";
import type { ApiPresetDefinition, ApiPresetProfile, ApiPresetProfileSummary } from "../api/presets";
import type { ApiRunSummary } from "../api/runs";
import { studioApi } from "../api/studioApi";
import { mockStudioApi } from "../api/mockStudioApi";
import { defaultEmbodimentParams } from "../mock/studioMock";
import type {
  ApplyPresetResponse,
  AssetDetail,
  DiffSummaryData,
  EmbodimentParameters,
  PresetOption,
  PresetProfileSummary,
  RunHistoryItem,
  SpriteMode,
  StudioAsset,
  ValidationData,
  ValidationMetric
} from "../types/studio";
import { useStudioApi } from "./useStudioApi";

const PLACEHOLDER_SPRITES = {
  front: "/placeholders/front.svg",
  back: "/placeholders/back.svg",
  side: "/placeholders/side.svg"
};

export function useStudioState() {
  const { mode, setMode, apiStatusMessage, setApiStatusMessage, checkBackend } = useStudioApi();
  const [assets, setAssets] = useState<StudioAsset[]>(mockStudioApi.listAssets());
  const [presetProfiles, setPresetProfiles] = useState<PresetProfileSummary[]>([
    {
      profileId: "fantasy_humanoid",
      displayName: "Fantasy Humanoid",
      presetIds: mockStudioApi.listPresets().map((preset) => preset.id)
    }
  ]);
  const [selectedPresetProfileId, setSelectedPresetProfileId] = useState("fantasy_humanoid");
  const [presets, setPresets] = useState<PresetOption[]>(mockStudioApi.listPresets());
  const [runs, setRuns] = useState<RunHistoryItem[]>(mockStudioApi.listRuns());
  const [selectedAssetId, setSelectedAssetId] = useState("hero_side_fixture");
  const [selectedPresetId, setSelectedPresetId] = useState("pull_hat_back");
  const [selectedRunId, setSelectedRunId] = useState(mockStudioApi.listRuns()[0]?.id ?? "");
  const [selectedAssetDetail, setSelectedAssetDetail] = useState<AssetDetail | null>(null);
  const [spriteMode, setSpriteMode] = useState<SpriteMode>("raw");
  const [intensity, setIntensity] = useState(0.75);
  const [embodimentParams, setEmbodimentParams] = useState<EmbodimentParameters>(defaultEmbodimentParams);
  const [lastAppliedPreset, setLastAppliedPreset] = useState<string | null>(null);
  const [diffSummary, setDiffSummary] = useState<DiffSummaryData>(mockStudioApi.getDiffSummary());
  const [validation, setValidation] = useState<ValidationData>(mockStudioApi.getValidation());
  const [isApplyingPreset, setIsApplyingPreset] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadInitialData() {
      const live = await checkBackend();
      if (!active || !live) {
        return;
      }

      try {
        const [assetResponse, profileResponse, runResponse] = await Promise.all([
          studioApi.listAssets(),
          studioApi.listPresetProfiles(),
          studioApi.listRuns()
        ]);
        if (!active) {
          return;
        }

        const mappedAssets = assetResponse.assets.map(mapApiAsset);
        const mappedProfiles = profileResponse.profiles.map(mapApiPresetProfileSummary);
        const preferredProfile =
          mappedProfiles.find((profile) => profile.profileId === "fantasy_humanoid") ?? mappedProfiles[0];
        const profile =
          preferredProfile != null
            ? await studioApi.getPresetProfile(preferredProfile.profileId)
            : { profile: null };
        if (!active) {
          return;
        }

        setAssets(mappedAssets.length > 0 ? mappedAssets : mockStudioApi.listAssets());
        setPresetProfiles(mappedProfiles.length > 0 ? mappedProfiles : []);
        if (preferredProfile) {
          setSelectedPresetProfileId(preferredProfile.profileId);
        }
        const mappedPresets = profile.profile ? mapApiPresetProfile(profile.profile) : mockStudioApi.listPresets();
        setPresets(mappedPresets.length > 0 ? mappedPresets : mockStudioApi.listPresets());
        setRuns(runResponse.runs.map(mapApiRunSummary));
        setSelectedAssetId((current) =>
          mappedAssets.some((asset) => asset.id === current) ? current : mappedAssets[0]?.id ?? "hero_side_fixture"
        );
        setSelectedPresetId((current) =>
          mappedPresets.some((preset) => preset.id === current) ? current : mappedPresets[0]?.id ?? "pull_hat_back"
        );
        setApiStatusMessage("LIVE mode: connected to Studio API.");
      } catch (error) {
        setMode("MOCK");
        setApiStatusMessage(
          error instanceof Error
            ? `Studio API data load failed; using mocks: ${error.message}`
            : "Studio API data load failed; using mocks."
        );
      }
    }

    loadInitialData();
    return () => {
      active = false;
    };
  }, [checkBackend, setApiStatusMessage, setMode]);

  useEffect(() => {
    let active = true;
    if (mode !== "LIVE" || !selectedAssetId) {
      setSelectedAssetDetail(null);
      return undefined;
    }

    studioApi
      .getAsset(selectedAssetId)
      .then((response) => {
        if (active) {
          setSelectedAssetDetail(mapApiAssetDetail(response.asset));
        }
      })
      .catch((error) => {
        if (active) {
          setWorkflowError(error instanceof Error ? error.message : "Unable to load asset detail.");
        }
      });

    return () => {
      active = false;
    };
  }, [mode, selectedAssetId]);

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) ?? assets[0],
    [assets, selectedAssetId]
  );
  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedPresetId) ?? presets[0],
    [presets, selectedPresetId]
  );
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? runs[0], [runs, selectedRunId]);

  const updateParam = (key: keyof EmbodimentParameters, value: number) => {
    setEmbodimentParams((current) => ({
      ...current,
      [key]: value
    }));
  };

  const applyPreset = useCallback(async () => {
    setWorkflowError(null);
    setIsApplyingPreset(true);
    try {
      if (mode === "LIVE") {
        const response = await studioApi.applyPreset({
          asset_id: selectedAssetId,
          base_params: preferredBaseParams(selectedAssetId, selectedAssetDetail),
          preset_profile: selectedPresetProfileId,
          preset_id: selectedPresetId,
          intensity,
          run_diff: true
        });
        const runId = response.run_id ?? response.runId ?? `run_${Date.now()}`;
        setLastAppliedPreset(`${selectedPresetId}@${intensity.toFixed(2)}`);
        setSelectedRunId(runId);
        setRuns((current) => [
          {
            id: runId,
            preset: selectedPresetId,
            asset: selectedAssetId,
            outDir: response.out_dir ?? undefined,
            hasPresetReport: Boolean(response.preset_application_report),
            hasParamDiffReport: Boolean(response.param_diff_report)
          },
          ...current.filter((run) => run.id !== runId)
        ]);
        setDiffSummary(diffFromApplyResponse(response));
        setValidation(validationFromApplyResponse(response));
      } else {
        const runId = `mock_${selectedPresetId}_${Date.now()}`;
        setLastAppliedPreset(`${selectedPresetId}@${intensity.toFixed(2)}`);
        setSelectedRunId(runId);
        setRuns((current) => [{ id: runId, preset: selectedPresetId, asset: selectedAssetId }, ...current]);
        setDiffSummary(mockStudioApi.getDiffSummary());
        setValidation(mockStudioApi.getValidation());
      }
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "Apply preset failed.");
    } finally {
      setIsApplyingPreset(false);
    }
  }, [
    intensity,
    mode,
    selectedAssetDetail,
    selectedAssetId,
    selectedPresetId,
    selectedPresetProfileId
  ]);

  const selectRun = useCallback(
    async (runId: string) => {
      const run = runs.find((item) => item.id === runId);
      if (!run) {
        return;
      }
      setSelectedRunId(runId);
      setSelectedAssetId(run.asset);
      setSelectedPresetId(run.preset);
      setLastAppliedPreset(`${run.preset}@history`);

      if (mode === "LIVE" && !runId.startsWith("mock_")) {
        try {
          const response = await studioApi.getRun(runId);
          setDiffSummary(diffFromRunDetail(response.run));
          setValidation(validationFromReports(response.run.param_diff_report, response.run.preset_application_report));
        } catch (error) {
          setWorkflowError(error instanceof Error ? error.message : "Unable to load run detail.");
        }
      }
    },
    [mode, runs]
  );

  return {
    mode,
    apiStatusMessage,
    workflowError,
    assets,
    presetProfiles,
    selectedPresetProfileId,
    setSelectedPresetProfileId,
    presets,
    runs,
    selectedAsset,
    selectedAssetId,
    setSelectedAssetId,
    selectedAssetDetail,
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
    isApplyingPreset,
    lastAppliedPreset,
    diffSummary,
    validation
  };
}

function mapApiAsset(asset: ApiAssetSummary): StudioAsset {
  return {
    id: asset.asset_id,
    coverage: coverageFromSource(asset.source_coverage, asset.available_sprites),
    sprites: PLACEHOLDER_SPRITES,
    path: asset.path,
    availableSprites: asset.available_sprites,
    sourceCoverage: asset.source_coverage
  };
}

function mapApiAssetDetail(asset: ApiAssetDetail): AssetDetail {
  return {
    assetId: asset.asset_id,
    path: asset.path,
    metadata: asset.metadata ?? {},
    semanticOverrideLabels: asset.semantic_override_labels ?? [],
    availableParamsFiles: asset.available_params_files ?? []
  };
}

function mapApiPresetProfileSummary(profile: ApiPresetProfileSummary): PresetProfileSummary {
  return {
    profileId: profile.profile_id,
    displayName: profile.display_name ?? profile.profile_id,
    path: profile.path,
    presetIds: profile.preset_ids ?? []
  };
}

function mapApiPresetProfile(profile: ApiPresetProfile): PresetOption[] {
  return (profile.presets ?? []).map((preset: ApiPresetDefinition) => ({
    id: preset.preset_id,
    displayName: preset.display_name ?? preset.preset_id,
    description: preset.description ?? preset.expected_effect ?? "",
    profileId: profile.profile_id
  }));
}

function mapApiRunSummary(run: ApiRunSummary): RunHistoryItem {
  return {
    id: run.run_id,
    preset: inferPresetFromRunId(run.run_id),
    asset: inferAssetFromRunId(run.run_id),
    outDir: run.out_dir,
    hasPresetReport: run.has_preset_report,
    hasParamDiffReport: run.has_param_diff_report
  };
}

function coverageFromSource(sourceCoverage?: Record<string, unknown>, availableSprites?: Record<string, boolean>): string {
  const sideAuthority = String(sourceCoverage?.side_geometry_authority ?? "");
  if (sideAuthority.includes("authored") || availableSprites?.left || availableSprites?.right) {
    return "front_back_side";
  }
  if (availableSprites?.back || sourceCoverage?.back === "authored") {
    return "front_back";
  }
  return "front_only";
}

function preferredBaseParams(assetId: string, detail: AssetDetail | null): string {
  const files = detail?.availableParamsFiles ?? [];
  return (
    files.find((file) => file.includes("embodiment_params_default")) ??
    files[0] ??
    `assets/samples/${assetId}/embodiment_params_default.json`
  );
}

function diffFromApplyResponse(response: ApplyPresetResponse): DiffSummaryData {
  return diffFromReports(response.param_diff_report, response.preset_application_report, response.summary_md ?? undefined);
}

function diffFromRunDetail(run: {
  param_diff_report?: Record<string, unknown>;
  preset_application_report?: Record<string, unknown>;
  summary_md?: string;
}): DiffSummaryData {
  return diffFromReports(run.param_diff_report, run.preset_application_report, run.summary_md);
}

function diffFromReports(
  paramDiff?: Record<string, unknown> | null,
  presetReport?: Record<string, unknown> | null,
  summaryMd?: string
): DiffSummaryData {
  const helpful = toStringList(paramDiff?.helpful_deltas);
  const harmful = toStringList(paramDiff?.harmful_deltas);
  const neutral = toStringList(paramDiff?.neutral_deltas);
  const skippedFromPreset = toStringList(presetReport?.skipped_parts);
  const skippedFromChanged = toStringList(
    Array.isArray((paramDiff?.changed_parts as Record<string, unknown> | undefined)?.skipped_parts)
      ? (paramDiff?.changed_parts as Record<string, unknown>).skipped_parts
      : []
  );

  return {
    helpful: helpful.length > 0 ? helpful : toStringList(presetReport?.applied_parts).map((part) => `${part}: applied`),
    harmful,
    neutral,
    skipped: [...skippedFromPreset, ...skippedFromChanged],
    summaryMd
  };
}

function validationFromApplyResponse(response: ApplyPresetResponse): ValidationData {
  return validationFromReports(response.param_diff_report, response.preset_application_report);
}

function validationFromReports(
  paramDiff?: Record<string, unknown> | null,
  presetReport?: Record<string, unknown> | null
): ValidationData {
  const editValid = readBoolean(paramDiff?.edit_valid);
  const hardGates = readBoolean(paramDiff?.edit_preserved_hard_gates);
  const changedGeometry = readBoolean(paramDiff?.edit_changed_geometry);
  const likelyImprovement = readBoolean(paramDiff?.likely_improvement);
  const validForAsset = readBoolean(presetReport?.valid_for_asset);

  const metrics: ValidationMetric[] = [
    {
      key: "edit_valid",
      value: editValid ?? "unknown",
      status: editValid === false ? "FAIL" : "PASS"
    },
    {
      key: "hard_gates_preserved",
      value: hardGates ?? "unknown",
      status: hardGates === false ? "FAIL" : "PASS"
    },
    {
      key: "geometry_changed",
      value: changedGeometry ?? "unknown",
      status: changedGeometry === false ? "WARNING" : "PASS"
    },
    {
      key: "likely_improvement",
      value: likelyImprovement ?? "unknown",
      status: likelyImprovement === false ? "WARNING" : "PASS"
    },
    {
      key: "valid_for_asset",
      value: validForAsset ?? "unknown",
      status: validForAsset === false ? "FAIL" : "PASS"
    }
  ];

  return {
    status: metrics.some((metric) => metric.status === "FAIL")
      ? "FAIL"
      : metrics.some((metric) => metric.status === "WARNING")
        ? "WARNING"
        : "PASS",
    metrics
  };
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => {
    if (typeof item === "string") {
      return item;
    }
    if (typeof item === "number" || typeof item === "boolean") {
      return String(item);
    }
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      const name = record.metric ?? record.name ?? record.part_id ?? record.part ?? record.reason ?? "delta";
      const delta = record.delta ?? record.value ?? record.change;
      return delta == null ? String(name) : `${String(name)} ${String(delta)}`;
    }
    return String(item);
  });
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function inferPresetFromRunId(runId: string): string {
  if (runId.includes("pull_hat_back")) {
    return "pull_hat_back";
  }
  if (runId.includes("thicken_torso")) {
    return "thicken_torso";
  }
  if (runId.includes("push_face_forward")) {
    return "push_face_forward";
  }
  if (runId.includes("widen_side_profile")) {
    return "widen_side_profile";
  }
  return "unknown";
}

function inferAssetFromRunId(runId: string): string {
  if (runId.includes("hero_side_fixture")) {
    return "hero_side_fixture";
  }
  if (runId.includes("hero")) {
    return "hero";
  }
  return "unknown";
}
