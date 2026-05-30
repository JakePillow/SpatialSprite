import { requestJson } from "./client";

export interface ApiPresetProfileSummary {
  profile_id: string;
  path?: string;
  display_name?: string;
  preset_ids?: string[];
}

export interface ApiPresetDefinition {
  preset_id: string;
  display_name?: string;
  description?: string;
  target_parts?: string[];
  expected_effect?: string;
  risk_notes?: string;
}

export interface ApiPresetProfile {
  profile_id: string;
  display_name?: string;
  description?: string;
  path?: string;
  presets?: ApiPresetDefinition[];
  raw?: Record<string, unknown>;
}

export async function listPresetProfiles() {
  return requestJson<{ ok: boolean; profiles: ApiPresetProfileSummary[] }>("/presets", { timeoutMs: 2500 });
}

export async function getPresetProfile(profileId: string) {
  return requestJson<{ ok: boolean; profile: ApiPresetProfile }>(`/presets/${encodeURIComponent(profileId)}`, {
    timeoutMs: 2500
  });
}
