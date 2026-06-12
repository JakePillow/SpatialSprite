export type AssetCoverage = "front_back" | "front_back_side";
export type StudioMode = "LIVE" | "MOCK";
export type ViewRole = "front" | "side" | "back" | "left" | "right";
export type ViewSelectionMode = "strict" | "prototype";

export interface StudioAsset {
  id: string;
  coverage: AssetCoverage | string;
  sprites: {
    front: string;
    back: string;
    side: string;
  };
  path?: string;
  availableSprites?: Record<string, boolean>;
  sourceCoverage?: Record<string, unknown>;
}

export interface PresetOption {
  id: string;
  displayName: string;
  description: string;
  profileId?: string;
}

export interface PresetProfileSummary {
  profileId: string;
  displayName: string;
  path?: string;
  presetIds: string[];
}

export interface AssetDetail {
  assetId: string;
  path: string;
  metadata: Record<string, unknown>;
  semanticOverrideLabels: Array<{
    label: string;
    path: string;
    nonempty: boolean;
  }>;
  availableParamsFiles: string[];
}

export interface EmbodimentParameters {
  z_center_offset: number;
  thickness_scale: number;
  front_bias: number;
  back_bias: number;
  side_width_scale: number;
  taper_strength: number;
}

export interface DiffSummaryData {
  helpful: string[];
  harmful: string[];
  skipped: string[];
  neutral?: string[];
  summaryMd?: string;
}

export type ValidationStatus = "PASS" | "WARNING" | "FAIL";

export interface ValidationMetric {
  key: string;
  value: string | number | boolean;
  status: ValidationStatus;
}

export interface ValidationData {
  status: ValidationStatus;
  metrics: ValidationMetric[];
}

export interface RunHistoryItem {
  id: string;
  preset: string;
  asset: string;
  outDir?: string;
  hasPresetReport?: boolean;
  hasParamDiffReport?: boolean;
  status?: string;
  createdAt?: string;
  validationPassed?: boolean | null;
}

export interface RawSheet {
  sheet_id: string;
  filename: string;
  path: string;
  width: number;
  height: number;
  size_bytes?: number;
}

export interface CandidateRecord {
  candidate_id: number;
  path: string;
  bbox?: number[];
  size?: number[];
  has_alpha?: boolean;
  alpha_coverage?: number;
  complete_score?: number;
  deterministic_pose_hint?: string;
}

export interface CandidateRun {
  run_id: string;
  out_dir: string;
  candidate_contact_sheet: string;
  candidates: CandidateRecord[];
  candidate_report?: Record<string, unknown>;
}

export type ViewAssignments = Partial<Record<ViewRole, number>>;

export interface CreateAssetResponse {
  ok: boolean;
  asset_id: string;
  asset_dir: string;
  spriteasset_path: string;
  created_files: string[];
  source_coverage?: Record<string, string>;
  view_selection_path?: string;
  warnings?: string[];
}

export interface BuildJob {
  job_id: string;
  asset_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at?: string;
  finished_at?: string | null;
  output_dir?: string;
  validation_report?: Record<string, unknown> | null;
  validation?: Record<string, unknown> | null;
  artifacts?: Record<string, string>;
  error?: string | null;
  validation_passed?: boolean | null;
}

export interface ApplyPresetResponse {
  ok: boolean;
  run_id?: string | null;
  runId?: string | null;
  out_dir?: string | null;
  edited_params_path?: string | null;
  preset_application_report?: Record<string, unknown> | null;
  param_diff_report?: Record<string, unknown> | null;
  summary_md?: string | null;
  paths?: Record<string, string>;
  error?: string | null;
}
