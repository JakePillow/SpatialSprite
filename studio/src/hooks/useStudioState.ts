import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiAssetDetail, ApiAssetSummary } from "../api/assets";
import { fileUrl } from "../api/sheets";
import type { ApiPresetDefinition, ApiPresetProfile, ApiPresetProfileSummary } from "../api/presets";
import type { ApiRunSummary } from "../api/runs";
import { studioApi } from "../api/studioApi";
import { mockStudioApi } from "../api/mockStudioApi";
import { defaultEmbodimentParams } from "../mock/studioMock";
import type {
  ApplyPresetResponse,
  AssetDetail,
  BuildJob,
  CandidateRecord,
  CandidateRun,
  CreateAssetResponse,
  DiffSummaryData,
  EmbodimentParameters,
  PresetOption,
  PresetProfileSummary,
  RawSheet,
  RunHistoryItem,
  StudioAsset,
  ValidationData,
  ValidationMetric,
  ViewAssignments,
  ViewRole,
  ViewSelectionMode
} from "../types/studio";
import { useStudioApi } from "./useStudioApi";

const PLACEHOLDER_SPRITES = {
  front: "/placeholders/front.svg",
  back: "/placeholders/back.svg",
  side: "/placeholders/side.svg"
};
const ASSET_ALREADY_EXISTS_PATTERN = /Asset already exists:\s*([a-z0-9_]+)/i;
const ASSET_ID_PATTERN = /^[a-z0-9_]+$/;
const ASSET_ORDER_KEY = "spritespatial.assetOrder";

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
  const [buildJobs, setBuildJobs] = useState<BuildJob[]>(mockStudioApi.listBuildJobs());
  const [selectedBuildJobId, setSelectedBuildJobId] = useState(mockStudioApi.listBuildJobs()[0]?.job_id ?? "");
  const [isStartingBuild, setIsStartingBuild] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [rawSheets, setRawSheets] = useState<RawSheet[]>(mockStudioApi.listRawSheets());
  const [isUploadingSheet, setIsUploadingSheet] = useState(false);
  const [sheetUploadError, setSheetUploadError] = useState<string | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState("hero_side_fixture");
  const [selectedPresetId, setSelectedPresetId] = useState("pull_hat_back");
  const [selectedSheetPath, setSelectedSheetPath] = useState(mockStudioApi.listRawSheets()[0]?.path ?? "");
  const [selectedRunId, setSelectedRunId] = useState(mockStudioApi.listRuns()[0]?.id ?? "");
  const [selectedAssetDetail, setSelectedAssetDetail] = useState<AssetDetail | null>(null);
  const [intensity, setIntensity] = useState(0.75);
  const [embodimentParams, setEmbodimentParams] = useState<EmbodimentParameters>(defaultEmbodimentParams);
  const [lastAppliedPreset, setLastAppliedPreset] = useState<string | null>(null);
  const [diffSummary, setDiffSummary] = useState<DiffSummaryData>(mockStudioApi.getDiffSummary());
  const [validation, setValidation] = useState<ValidationData>(mockStudioApi.getValidation());
  const [isApplyingPreset, setIsApplyingPreset] = useState(false);
  const [isExtractingCandidates, setIsExtractingCandidates] = useState(false);
  const [candidateRun, setCandidateRun] = useState<CandidateRun | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [viewAssignments, setViewAssignments] = useState<ViewAssignments>({});
  const [activeViewRole, setActiveViewRole] = useState<ViewRole>("front");
  const [viewSelectionMode, setViewSelectionMode] = useState<ViewSelectionMode>("strict");
  const [newAssetId, setNewAssetId] = useState(() => generateAssetId("my_character"));
  const [isCreatingAsset, setIsCreatingAsset] = useState(false);
  const [assetCreationResult, setAssetCreationResult] = useState<CreateAssetResponse | null>(null);
  const [assetCreationError, setAssetCreationError] = useState<string | null>(null);
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
        const sheetResponse = await studioApi.listRawSheets();
        const jobsResponse = await studioApi.listJobs();
        if (!active) {
          return;
        }

        const mappedAssets = assetResponse.assets.map(mapApiAsset);
        const mappedProfiles = profileResponse.profiles.map(mapApiPresetProfileSummary);
        const mappedSheets = sheetResponse.sheets ?? [];
        const mappedJobs = jobsResponse.jobs ?? [];
        const preferredProfile =
          mappedProfiles.find((profile) => profile.profileId === "fantasy_humanoid") ?? mappedProfiles[0];
        const profile =
          preferredProfile != null
            ? await studioApi.getPresetProfile(preferredProfile.profileId)
            : { profile: null };
        if (!active) {
          return;
        }

        setAssets(applyAssetOrder(mappedAssets.length > 0 ? mappedAssets : mockStudioApi.listAssets()));
        setRawSheets(mappedSheets.length > 0 ? mappedSheets : mockStudioApi.listRawSheets());
        setSelectedSheetPath((current) =>
          mappedSheets.some((sheet) => sheet.path === current) ? current : mappedSheets[0]?.path ?? current
        );
        setPresetProfiles(mappedProfiles.length > 0 ? mappedProfiles : []);
        if (preferredProfile) {
          setSelectedPresetProfileId(preferredProfile.profileId);
        }
        const mappedPresets = profile.profile ? mapApiPresetProfile(profile.profile) : mockStudioApi.listPresets();
        setPresets(mappedPresets.length > 0 ? mappedPresets : mockStudioApi.listPresets());
        setRuns(runResponse.runs.map(mapApiRunSummary));
        setBuildJobs(mappedJobs);
        setSelectedBuildJobId((current) =>
          mappedJobs.some((job) => job.job_id === current) ? current : mappedJobs[0]?.job_id ?? current
        );
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
  const selectedSheet = useMemo(
    () => rawSheets.find((sheet) => sheet.path === selectedSheetPath) ?? rawSheets[0],
    [rawSheets, selectedSheetPath]
  );
  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedPresetId) ?? presets[0],
    [presets, selectedPresetId]
  );
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? runs[0], [runs, selectedRunId]);
  const selectedBuildJob = useMemo(
    () => {
      const selected = buildJobs.find((job) => job.job_id === selectedBuildJobId && job.asset_id === selectedAssetId);
      if (selected) {
        return selected;
      }
      return buildJobs.find((job) => job.asset_id === selectedAssetId) ?? null;
    },
    [buildJobs, selectedAssetId, selectedBuildJobId]
  );
  const buildRunItems = useMemo(() => buildJobs.map(mapBuildJobToRun), [buildJobs]);
  const selectedCandidate = useMemo(
    () => candidateRun?.candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ?? null,
    [candidateRun, selectedCandidateId]
  );

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

  const selectSheet = useCallback((sheet: RawSheet) => {
    setSelectedSheetPath(sheet.path);
    setCandidateRun(null);
    setSelectedCandidateId(null);
    setViewAssignments({});
  }, []);

  const selectAsset = useCallback((assetId: string) => {
    setSelectedAssetId(assetId);
    setSelectedBuildJobId("");
    setBuildError(null);
  }, []);

  const uploadSheet = useCallback(
    async (file: File) => {
      setWorkflowError(null);
      setSheetUploadError(null);
      setIsUploadingSheet(true);
      try {
        if (mode !== "LIVE") {
          throw new Error("Sheet upload requires the local Studio API to be running.");
        }
        const response = await studioApi.uploadRawSheet(file);
        const sheetsResponse = await studioApi.listRawSheets();
        setRawSheets(sheetsResponse.sheets);
        selectSheet(response.sheet);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Sheet upload failed.";
        setSheetUploadError(message);
        setWorkflowError(message);
      } finally {
        setIsUploadingSheet(false);
      }
    },
    [mode, selectSheet]
  );

  const extractCandidates = useCallback(async () => {
    if (!selectedSheet) {
      return;
    }
    const extractionAssetId = /^[a-z0-9_]+$/.test(newAssetId) ? newAssetId : selectedAssetId;
    setWorkflowError(null);
    setIsExtractingCandidates(true);
    setViewAssignments({});
    try {
      if (mode === "LIVE") {
        const response = await studioApi.extractViewCandidates({
          sheet_path: selectedSheet.path,
          asset_id: extractionAssetId,
          max_candidates: 320,
          ai_rank: false
        });
        const run: CandidateRun = {
          run_id: response.run_id,
          out_dir: response.out_dir,
          candidate_contact_sheet: response.candidate_contact_sheet,
          candidate_report: response.candidate_report,
          candidates: response.candidates ?? []
        };
        setCandidateRun(run);
        setSelectedCandidateId(run.candidates[0]?.candidate_id ?? null);
      } else {
        const run = mockCandidateRun();
        setCandidateRun(run);
        setSelectedCandidateId(run.candidates[0]?.candidate_id ?? null);
      }
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "Candidate extraction failed.");
    } finally {
      setIsExtractingCandidates(false);
    }
  }, [mode, newAssetId, selectedAssetId, selectedSheet]);

  const assignCandidateToView = useCallback((role: ViewRole, candidateId: number) => {
    setViewAssignments((current) => ({ ...current, [role]: candidateId }));
    if (role === "front") {
      setActiveViewRole("side");
    } else if (role === "side") {
      setActiveViewRole("back");
    }
  }, []);

  const selectCandidateForActiveView = useCallback(
    (candidate: CandidateRecord) => {
      setSelectedCandidateId(candidate.candidate_id);
      if (activeViewRole === "front" || activeViewRole === "side" || activeViewRole === "back") {
        assignCandidateToView(activeViewRole, candidate.candidate_id);
      }
    },
    [activeViewRole, assignCandidateToView]
  );

  const clearViewAssignment = useCallback((role: ViewRole) => {
    setViewAssignments((current) => {
      const next = { ...current };
      delete next[role];
      return next;
    });
  }, []);

  const createAssetFromCandidates = useCallback(async (): Promise<CreateAssetResponse | null> => {
    if (!candidateRun) {
      return null;
    }
    setAssetCreationError(null);
    setAssetCreationResult(null);
    setWorkflowError(null);
    setIsCreatingAsset(true);
    try {
      if (mode === "LIVE") {
        const response = await studioApi.createAssetFromCandidates({
          asset_id: newAssetId,
          candidate_run_dir: candidateRun.out_dir,
          selection_version: "view_selection_v1",
          mode: viewSelectionMode,
          selection: viewAssignments,
          source_coverage: sourceCoverageFromAssignments(viewAssignments)
        });
        setAssetCreationResult(response);
        const assetResponse = await studioApi.listAssets();
        const mappedAssets = assetResponse.assets.map(mapApiAsset);
        setAssets((current) => ensureAssetInList(mappedAssets.length > 0 ? mappedAssets : current, assetFromCreateResponse(response)));
        setSelectedAssetId(response.asset_id);
        setSelectedBuildJobId("");
        return response;
      } else {
        const response: CreateAssetResponse = {
          ok: true,
          asset_id: newAssetId,
          asset_dir: `assets/samples/${newAssetId}`,
          spriteasset_path: `assets/samples/${newAssetId}/spriteasset_v1.json`,
          created_files: [],
          source_coverage: sourceCoverageFromAssignments(viewAssignments),
          view_selection_path: `assets/samples/${newAssetId}/view_selection_v1.json`,
          warnings: viewSelectionWarnings(viewAssignments, viewSelectionMode)
        };
        setAssetCreationResult(response);
        setAssets((current) => [
          {
            id: newAssetId,
            coverage: viewAssignments.side != null ? "front_back_side" : "front_back",
            sprites: PLACEHOLDER_SPRITES,
            sourceCoverage: response.source_coverage
          },
          ...current.filter((asset) => asset.id !== newAssetId)
        ]);
        setSelectedAssetId(newAssetId);
        setSelectedBuildJobId("");
        return response;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Create asset failed.";
      const existingMatch = message.match(ASSET_ALREADY_EXISTS_PATTERN);
      if (existingMatch) {
        const nextId = generateAssetId(existingMatch[1]);
        const duplicateMessage = `Asset id already exists. Suggested new id: ${nextId}`;
        setNewAssetId(nextId);
        setAssetCreationError(duplicateMessage);
        setWorkflowError(duplicateMessage);
      } else {
        setAssetCreationError(message);
        setWorkflowError(message);
      }
      return null;
    } finally {
      setIsCreatingAsset(false);
    }
  }, [candidateRun, mode, newAssetId, viewAssignments, viewSelectionMode]);

  const generateNewAssetId = useCallback(() => {
    setAssetCreationError(null);
    setWorkflowError(null);
    setNewAssetId(generateAssetId(newAssetId || "my_character"));
  }, [newAssetId]);

  const startNewAsset = useCallback(() => {
    setNewAssetId(generateAssetId("my_character"));
    setViewAssignments({});
    setSelectedCandidateId(null);
    setActiveViewRole("front");
    setViewSelectionMode("strict");
    setAssetCreationResult(null);
    setAssetCreationError(null);
    setBuildError(null);
    setSelectedBuildJobId("");
    setWorkflowError(null);
  }, []);

  const renameAsset = useCallback(
    async (assetId: string, newAssetId: string) => {
      const nextId = newAssetId.trim();
      if (!ASSET_ID_PATTERN.test(nextId)) {
        setWorkflowError("Asset id must use lowercase letters, numbers, and underscore only.");
        return;
      }
      setWorkflowError(null);
      try {
        replaceAssetOrderId(assetId, nextId);
        if (mode === "LIVE") {
          await studioApi.renameAsset(assetId, nextId);
          const response = await studioApi.listAssets();
          setAssets(applyAssetOrder(response.assets.map(mapApiAsset)));
        } else {
          setAssets((current) =>
            current.map((asset) => (asset.id === assetId ? { ...asset, id: nextId } : asset))
          );
        }
        setSelectedAssetId((current) => (current === assetId ? nextId : current));
        setBuildJobs((current) => current.map((job) => (job.asset_id === assetId ? { ...job, asset_id: nextId } : job)));
        setRuns((current) => current.map((run) => (run.asset === assetId ? { ...run, asset: nextId } : run)));
      } catch (error) {
        setWorkflowError(error instanceof Error ? error.message : "Rename asset failed.");
      }
    },
    [mode]
  );

  const deleteAsset = useCallback(
    async (assetId: string) => {
      setWorkflowError(null);
      try {
        if (mode === "LIVE") {
          await studioApi.deleteAsset(assetId);
        }
        removeAssetOrderId(assetId);
        setAssets((current) => {
          const next = current.filter((asset) => asset.id !== assetId);
          if (selectedAssetId === assetId) {
            setSelectedAssetId(next[0]?.id ?? "");
            setSelectedBuildJobId("");
          }
          return next;
        });
      } catch (error) {
        setWorkflowError(error instanceof Error ? error.message : "Delete asset failed.");
      }
    },
    [mode, selectedAssetId]
  );

  const moveAsset = useCallback((assetId: string, direction: "up" | "down") => {
    setAssets((current) => {
      const index = current.findIndex((asset) => asset.id === assetId);
      const target = direction === "up" ? index - 1 : index + 1;
      if (index < 0 || target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      const [asset] = next.splice(index, 1);
      next.splice(target, 0, asset);
      persistAssetOrder(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        return;
      }
      const selected = selectedCandidate;
      if (event.key.toLowerCase() === "f" && selected) {
        assignCandidateToView("front", selected.candidate_id);
      } else if (event.key.toLowerCase() === "s" && selected) {
        assignCandidateToView("side", selected.candidate_id);
      } else if (event.key.toLowerCase() === "b" && selected) {
        assignCandidateToView("back", selected.candidate_id);
      } else if (event.key.toLowerCase() === "r") {
        clearViewAssignment(activeViewRole);
      } else {
        return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeViewRole, assignCandidateToView, clearViewAssignment, selectedCandidate]);

  useEffect(() => {
    if (mode !== "LIVE" || !selectedBuildJobId) {
      return undefined;
    }
    const selected = buildJobs.find((job) => job.job_id === selectedBuildJobId);
    if (!selected || !["queued", "running"].includes(selected.status)) {
      return undefined;
    }
    let active = true;
    const poll = async () => {
      try {
        const response = await studioApi.getJob(selectedBuildJobId);
        if (!active) {
          return;
        }
        setBuildJobs((current) => upsertJob(current, response.job));
        if (response.job.status === "completed" || response.job.status === "failed") {
          setValidation(validationFromBuildJob(response.job));
        }
      } catch (error) {
        if (active) {
          setBuildError(error instanceof Error ? error.message : "Unable to poll build job.");
        }
      }
    };
    poll();
    const interval = window.setInterval(poll, 2000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [buildJobs, mode, selectedBuildJobId]);

  const startBuildForAsset = useCallback(async (assetId: string) => {
    setBuildError(null);
    setWorkflowError(null);
    setIsStartingBuild(true);
    try {
      if (mode === "LIVE") {
        const response = await studioApi.startBuildAsset(assetId);
        const detail = await studioApi.getJob(response.job_id);
        setBuildJobs((current) => upsertJob(current, detail.job));
        setSelectedBuildJobId(response.job_id);
      } else {
        const job: BuildJob = mockCompletedBuildJob(assetId);
        setBuildJobs((current) => upsertJob(current, job));
        setSelectedBuildJobId(job.job_id);
        setValidation(validationFromBuildJob(job));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Build asset failed.";
      setBuildError(message);
      setWorkflowError(message);
    } finally {
      setIsStartingBuild(false);
    }
  }, [mode]);

  const startBuildAsset = useCallback(async () => {
    await startBuildForAsset(selectedAssetId);
  }, [selectedAssetId, startBuildForAsset]);

  const createAssetAndBuild = useCallback(async () => {
    const response = await createAssetFromCandidates();
    if (!response) {
      return;
    }
    await startBuildForAsset(response.asset_id);
  }, [createAssetFromCandidates, startBuildForAsset]);

  const selectBuildJob = useCallback(
    async (jobId: string) => {
      setSelectedBuildJobId(jobId);
      const local = buildJobs.find((job) => job.job_id === jobId);
      if (local) {
        setSelectedAssetId(local.asset_id);
        setValidation(validationFromBuildJob(local));
      }
      if (mode === "LIVE") {
        try {
          const response = await studioApi.getJob(jobId);
          setBuildJobs((current) => upsertJob(current, response.job));
          setValidation(validationFromBuildJob(response.job));
          setSelectedAssetId(response.job.asset_id);
        } catch (error) {
          setBuildError(error instanceof Error ? error.message : "Unable to load build job.");
        }
      }
    },
    [buildJobs, mode]
  );

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

  const reconnectApi = useCallback(async () => {
    setWorkflowError(null);
    const live = await checkBackend();
    if (live) {
      window.location.reload();
    }
  }, [checkBackend]);

  return {
    mode,
    apiStatusMessage,
    workflowError,
    reconnectApi,
    assets,
    presetProfiles,
    selectedPresetProfileId,
    setSelectedPresetProfileId,
    presets,
    runs,
    buildJobs,
    buildRunItems,
    selectedBuildJob,
    selectedBuildJobId,
    selectBuildJob,
    startBuildAsset,
    isStartingBuild,
    buildError,
    rawSheets,
    isUploadingSheet,
    sheetUploadError,
    selectedSheet,
    selectedSheetPath,
    selectSheet,
    uploadSheet,
    candidateRun,
    selectedCandidate,
    selectedCandidateId,
    setSelectedCandidateId,
    selectCandidateForActiveView,
    viewAssignments,
    activeViewRole,
    setActiveViewRole,
    viewSelectionMode,
    setViewSelectionMode,
    viewSelectionWarnings: viewSelectionWarnings(viewAssignments, viewSelectionMode, candidateRun?.candidates ?? []),
    extractCandidates,
    isExtractingCandidates,
    assignCandidateToView,
    clearViewAssignment,
    newAssetId,
    setNewAssetId,
    generateNewAssetId,
    startNewAsset,
    createAssetFromCandidates,
    createAssetAndBuild,
    isCreatingAsset,
    assetCreationResult,
    assetCreationError,
    selectedAsset,
    selectedAssetId,
    setSelectedAssetId,
    selectAsset,
    renameAsset,
    deleteAsset,
    moveAsset,
    selectedAssetDetail,
    selectedPreset,
    selectedPresetId,
    setSelectedPresetId,
    selectedRun,
    selectedRunId,
    selectRun,
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

function mockCandidateRun(): CandidateRun {
  const candidates: CandidateRecord[] = [
    {
      candidate_id: 0,
      path: "/placeholders/front.svg",
      size: [32, 32],
      alpha_coverage: 0.35,
      deterministic_pose_hint: "front"
    },
    {
      candidate_id: 1,
      path: "/placeholders/back.svg",
      size: [32, 32],
      alpha_coverage: 0.34,
      deterministic_pose_hint: "back"
    },
    {
      candidate_id: 2,
      path: "/placeholders/side.svg",
      size: [32, 32],
      alpha_coverage: 0.28,
      deterministic_pose_hint: "side"
    },
    {
      candidate_id: 3,
      path: "/placeholders/side.svg",
      size: [32, 32],
      alpha_coverage: 0.28,
      deterministic_pose_hint: "side"
    }
  ];
  return {
    run_id: "mock_view_candidates",
    out_dir: "mock",
    candidate_contact_sheet: "/placeholders/front.svg",
    candidates
  };
}

function generateAssetId(base: string): string {
  const safeBase = base
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
  const prefix = safeBase || "my_character";
  const suffix = Date.now().toString(36).slice(-6);
  return `${prefix}_${suffix}`;
}

function applyAssetOrder(assets: StudioAsset[]): StudioAsset[] {
  const order = readAssetOrder();
  if (order.length === 0) {
    return assets;
  }
  const rank = new Map(order.map((assetId, index) => [assetId, index]));
  return [...assets].sort((left, right) => {
    const leftRank = rank.get(left.id) ?? Number.MAX_SAFE_INTEGER;
    const rightRank = rank.get(right.id) ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return assets.indexOf(left) - assets.indexOf(right);
  });
}

function persistAssetOrder(assets: StudioAsset[]): void {
  writeAssetOrder(assets.map((asset) => asset.id));
}

function replaceAssetOrderId(assetId: string, newAssetId: string): void {
  const order = readAssetOrder();
  if (order.length === 0) {
    return;
  }
  writeAssetOrder(order.map((id) => (id === assetId ? newAssetId : id)));
}

function removeAssetOrderId(assetId: string): void {
  const order = readAssetOrder();
  if (order.length === 0) {
    return;
  }
  writeAssetOrder(order.filter((id) => id !== assetId));
}

function readAssetOrder(): string[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(ASSET_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeAssetOrder(order: string[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(ASSET_ORDER_KEY, JSON.stringify(order));
  } catch {
    // Non-critical UI preference.
  }
}

function mockCompletedBuildJob(assetId: string): BuildJob {
  const jobId = `build_mock_${Date.now()}`;
  return {
    job_id: jobId,
    asset_id: assetId,
    status: "completed",
    created_at: new Date().toISOString(),
    output_dir: `outputs/studio_builds/${jobId}`,
    validation_passed: true,
    validation_report: {
      passed: true,
      mesh_connected_components: 1,
      degenerate_face_count: 0,
      non_manifold_after_cleanup: 0,
      semantic_label_preservation_passed: true
    },
    artifacts: {}
  };
}

function upsertJob(current: BuildJob[], job: BuildJob): BuildJob[] {
  return [job, ...current.filter((item) => item.job_id !== job.job_id)];
}

function mapBuildJobToRun(job: BuildJob): RunHistoryItem {
  return {
    id: job.job_id,
    preset: "build",
    asset: job.asset_id,
    outDir: job.output_dir,
    status: job.status,
    createdAt: job.created_at,
    validationPassed: readBuildPassed(job)
  };
}

function readBuildPassed(job: BuildJob): boolean | null {
  const validation = job.validation_report ?? job.validation;
  return typeof validation?.passed === "boolean" ? validation.passed : job.validation_passed ?? null;
}

function validationFromBuildJob(job: BuildJob): ValidationData {
  const validation = (job.validation_report ?? job.validation ?? {}) as Record<string, unknown>;
  const keys = [
    "passed",
    "mesh_connected_components",
    "degenerate_face_count",
    "non_manifold_after_cleanup",
    "semantic_label_preservation_passed",
    "hat_asymmetry_ratio"
  ];
  const metrics: ValidationMetric[] = keys
    .filter((key) => validation[key] !== undefined)
    .map((key) => {
      const value = validation[key] as string | number | boolean;
      return {
        key,
        value,
        status: metricStatus(key, value)
      };
    });
  if (metrics.length === 0) {
    metrics.push({
      key: "build_status",
      value: job.status,
      status: job.status === "failed" ? "FAIL" : job.status === "completed" ? "PASS" : "WARNING"
    });
  }
  return {
    status: metrics.some((metric) => metric.status === "FAIL")
      ? "FAIL"
      : metrics.some((metric) => metric.status === "WARNING")
        ? "WARNING"
        : "PASS",
    metrics
  };
}

function metricStatus(key: string, value: string | number | boolean): ValidationMetric["status"] {
  if (key === "passed" || key === "semantic_label_preservation_passed") {
    return value === false ? "FAIL" : "PASS";
  }
  if (key === "mesh_connected_components") {
    return Number(value) === 1 ? "PASS" : "FAIL";
  }
  if (key === "degenerate_face_count") {
    return Number(value) === 0 ? "PASS" : "FAIL";
  }
  if (key === "non_manifold_after_cleanup") {
    return Number(value) > 0 ? "WARNING" : "PASS";
  }
  return "PASS";
}

function sourceCoverageFromAssignments(assignments: ViewAssignments): Record<string, string> {
  const duplicateIds = duplicatedAssignmentIds(assignments);
  return {
    front: assignments.front == null ? "missing" : "authored",
    back: assignments.back == null ? "missing" : "authored",
    left:
      assignments.side == null
        ? "missing"
        : duplicateIds.has(assignments.side)
          ? "placeholder"
          : "authored_side",
    right:
      assignments.side == null
        ? "missing"
        : duplicateIds.has(assignments.side)
          ? "placeholder"
          : "authored_side",
    candidate_selection_method: "studio_manual"
  };
}

function viewSelectionWarnings(
  assignments: ViewAssignments,
  mode: ViewSelectionMode,
  candidates: CandidateRecord[] = []
): string[] {
  const warnings: string[] = [];
  const duplicateIds = duplicatedAssignmentIds({
    front: assignments.front,
    side: assignments.side,
    back: assignments.back
  });
  if (duplicateIds.size > 0) {
    warnings.push("Same candidate used for multiple views.");
  }
  if (mode === "prototype" && assignments.back == null) {
    warnings.push("Back will be inferred. Fidelity will be limited.");
  }
  if (mode === "prototype" && assignments.side == null) {
    warnings.push("Side will be inferred. Fidelity will be limited.");
  }
  for (const role of ["front", "side", "back"] as const) {
    const candidate = candidates.find((item) => item.candidate_id === assignments[role]);
    if (!candidate?.size || candidate.size.length < 2) {
      continue;
    }
    const [width, height] = candidate.size;
    if (width < 12 || height < 12) {
      warnings.push("Candidate may be too small.");
    }
    if (width > 256 || height > 256 || width / Math.max(1, height) > 3 || height / Math.max(1, width) > 3) {
      warnings.push("Candidate may not be a clean sprite crop.");
    }
  }
  const front = candidates.find((item) => item.candidate_id === assignments.front);
  const side = candidates.find((item) => item.candidate_id === assignments.side);
  if (front?.size && side?.size && front.size[0] === side.size[0] && front.size[1] === side.size[1]) {
    warnings.push("Side may be front-like. Confirm manually.");
  }
  return [...new Set(warnings)];
}

function duplicatedAssignmentIds(assignments: ViewAssignments): Set<number> {
  const counts = new Map<number, number>();
  for (const value of Object.values(assignments)) {
    if (value == null) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([candidateId]) => candidateId));
}

function mapApiAsset(asset: ApiAssetSummary): StudioAsset {
  const assetDir = asset.path.replace(/\/spriteasset_v1\.json$/, "");
  return {
    id: asset.asset_id,
    coverage: coverageFromSource(asset.source_coverage, asset.available_sprites),
    sprites: {
      front: fileUrl(`${assetDir}/front.png`),
      back: fileUrl(`${assetDir}/back.png`),
      side: fileUrl(`${assetDir}/side.png`)
    },
    path: asset.path,
    availableSprites: asset.available_sprites,
    sourceCoverage: asset.source_coverage
  };
}

function assetFromCreateResponse(response: CreateAssetResponse): StudioAsset {
  return {
    id: response.asset_id,
    coverage: response.source_coverage?.left === "authored_side" ? "front_back_side" : "front_back",
    sprites: {
      front: fileUrl(`${response.asset_dir}/front.png`),
      back: fileUrl(`${response.asset_dir}/back.png`),
      side: fileUrl(`${response.asset_dir}/side.png`)
    },
    path: response.spriteasset_path,
    availableSprites: {
      front: true,
      back: true,
      side: true
    },
    sourceCoverage: response.source_coverage
  };
}

function ensureAssetInList(assets: StudioAsset[], asset: StudioAsset): StudioAsset[] {
  return [asset, ...assets.filter((item) => item.id !== asset.id)];
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
