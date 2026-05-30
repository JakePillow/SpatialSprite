import { requestJson } from "./client";

export interface ApiRunSummary {
  run_id: string;
  out_dir?: string;
  has_preset_report?: boolean;
  has_param_diff_report?: boolean;
  created_at?: string;
}

export interface ApiRunDetail {
  run_id: string;
  out_dir?: string;
  preset_application_report?: Record<string, unknown>;
  param_diff_report?: Record<string, unknown>;
  summary_md?: string;
  paths?: Record<string, string>;
}

export async function listRuns() {
  return requestJson<{ ok: boolean; runs: ApiRunSummary[] }>("/runs", { timeoutMs: 2500 });
}

export async function getRun(runId: string) {
  return requestJson<{ ok: boolean; run: ApiRunDetail }>(`/runs/${encodeURIComponent(runId)}`, { timeoutMs: 2500 });
}
