import type { CandidateRecord, RawSheet } from "../types/studio";
import { getApiBase, requestJson } from "./client";

export interface ViewCandidatesPayload {
  sheet_path: string;
  asset_id: string;
  max_candidates: number;
  ai_rank: boolean;
}

export interface ViewCandidatesResponse {
  ok: boolean;
  run_id: string;
  out_dir: string;
  candidate_contact_sheet: string;
  candidate_report?: Record<string, unknown>;
  candidates: CandidateRecord[];
}

export async function listRawSheets() {
  return requestJson<{ ok: boolean; sheets: RawSheet[] }>("/raw-sheets", { timeoutMs: 2500 });
}

export async function uploadRawSheet(file: File) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${getApiBase()}/raw-sheets/upload?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      body: file,
      signal: controller.signal,
      headers: {
        "Content-Type": file.type || "application/octet-stream"
      }
    });
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`Studio API ${response.status} for raw sheet upload${body ? `: ${body.slice(0, 240)}` : ""}`);
    }
    return (await response.json()) as { ok: boolean; sheet: RawSheet };
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function extractViewCandidates(payload: ViewCandidatesPayload) {
  return requestJson<ViewCandidatesResponse>("/view-candidates", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 120000
  });
}

export function fileUrl(path?: string | null): string {
  if (!path) {
    return "";
  }
  if (path.startsWith("/") || path.startsWith("data:") || path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${getApiBase()}/file?path=${encodeURIComponent(path)}`;
}
