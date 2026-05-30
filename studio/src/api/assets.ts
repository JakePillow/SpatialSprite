import { requestJson } from "./client";

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
