import { requestJson } from "./client";
import type { CreateAssetResponse, ViewAssignments, ViewSelectionMode } from "../types/studio";

export interface ApiAssetSummary {
  asset_id: string;
  path: string;
  available_sprites?: Record<string, boolean>;
  source_coverage?: Record<string, unknown>;
}

export interface ApiAssetDetail {
  asset_id: string;
  path: string;
  metadata?: Record<string, unknown>;
  semantic_override_labels?: Array<{
    label: string;
    path: string;
    nonempty: boolean;
  }>;
  available_params_files?: string[];
}

export async function listAssets() {
  return requestJson<{ ok: boolean; assets: ApiAssetSummary[] }>("/assets", { timeoutMs: 2500 });
}

export async function getAsset(assetId: string) {
  return requestJson<{ ok: boolean; asset: ApiAssetDetail }>(`/assets/${encodeURIComponent(assetId)}`, {
    timeoutMs: 2500
  });
}

export interface CreateAssetFromCandidatesPayload {
  asset_id: string;
  candidate_run_dir: string;
  selection_version: "view_selection_v1";
  mode: ViewSelectionMode;
  selection: ViewAssignments;
  source_coverage: Record<string, string>;
}

export async function createAssetFromCandidates(payload: CreateAssetFromCandidatesPayload) {
  return requestJson<CreateAssetResponse>("/assets/from-candidates", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 30000
  });
}

export async function renameAsset(assetId: string, newAssetId: string) {
  return requestJson<{ ok: boolean; asset: ApiAssetDetail }>(`/assets/${encodeURIComponent(assetId)}`, {
    method: "PATCH",
    body: JSON.stringify({ new_asset_id: newAssetId }),
    timeoutMs: 10000
  });
}

export async function deleteAsset(assetId: string) {
  const path = `/assets/${encodeURIComponent(assetId)}`;
  try {
    return await requestJson<{ ok: boolean; asset_id: string }>(path, {
      method: "DELETE",
      timeoutMs: 10000
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (!message.includes("405")) {
      throw error;
    }
    return requestJson<{ ok: boolean; asset_id: string }>(`${path}/delete`, {
      method: "POST",
      timeoutMs: 10000
    });
  }
}
