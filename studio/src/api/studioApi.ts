import type { ApplyPresetResponse } from "../types/studio";
import { createAssetFromCandidates, deleteAsset, getAsset, listAssets, renameAsset } from "./assets";
import { requestJson } from "./client";
import { getJob, listJobs, startBuildAsset } from "./jobs";
import { getPresetProfile, listPresetProfiles } from "./presets";
import { getRun, listRuns } from "./runs";
import { extractViewCandidates, listRawSheets, uploadRawSheet } from "./sheets";

export interface ApplyPresetPayload {
  asset_id: string;
  base_params: string;
  preset_profile: string;
  preset_id: string;
  intensity: number;
  run_diff: boolean;
}

export interface RunDiffPayload {
  asset_id: string;
  base_params: string;
  edited_params: string;
  label_base: string;
  label_edited: string;
}

export async function health() {
  return requestJson<{ ok: boolean; service: string; version: string; local_only: boolean }>("/health", {
    timeoutMs: 1500
  });
}

export async function applyPreset(payload: ApplyPresetPayload) {
  return requestJson<ApplyPresetResponse>("/apply-preset", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 120000
  });
}

export async function runDiff(payload: RunDiffPayload) {
  return requestJson<ApplyPresetResponse>("/run-diff", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 120000
  });
}

export const studioApi = {
  health,
  listAssets,
  getAsset,
  createAssetFromCandidates,
  renameAsset,
  deleteAsset,
  listPresetProfiles,
  getPresetProfile,
  applyPreset,
  runDiff,
  listRuns,
  getRun,
  listRawSheets,
  uploadRawSheet,
  extractViewCandidates,
  startBuildAsset,
  listJobs,
  getJob
};
