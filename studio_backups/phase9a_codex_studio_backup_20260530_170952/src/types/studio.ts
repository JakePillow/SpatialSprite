export type AssetCoverage = "front_back" | "front_back_side";

export interface StudioAsset {
  id: string;
  coverage: AssetCoverage;
  sprites: {
    front: string;
    back: string;
    side: string;
  };
}

export interface PresetOption {
  id: string;
  displayName: string;
  description: string;
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
}

export type SpriteMode = "raw" | "semantic";
