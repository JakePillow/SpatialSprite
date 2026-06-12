import type { BuildJob } from "../types/studio";
import { requestJson } from "./client";

export async function startBuildAsset(assetId: string) {
  return requestJson<{ ok: boolean; job_id: string; status: BuildJob["status"] }>("/jobs/build-asset", {
    method: "POST",
    body: JSON.stringify({ asset_id: assetId }),
    timeoutMs: 5000
  });
}

export async function listJobs() {
  return requestJson<{ ok: boolean; jobs: BuildJob[] }>("/jobs", { timeoutMs: 2500 });
}

export async function getJob(jobId: string) {
  return requestJson<{ ok: boolean; job: BuildJob }>(`/jobs/${encodeURIComponent(jobId)}`, {
    timeoutMs: 2500
  });
}
