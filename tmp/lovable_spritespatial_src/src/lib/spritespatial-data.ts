export interface Asset {
  id: string;
  coverage: string;
}

export interface Run {
  id: string;
  preset: string;
  asset: string;
}

export type Preset =
  | "pull_hat_back"
  | "thicken_torso"
  | "push_face_forward"
  | "widen_side_profile";

export const PRESETS: Preset[] = [
  "pull_hat_back",
  "thicken_torso",
  "push_face_forward",
  "widen_side_profile",
];

export const MOCK_ASSETS: Asset[] = [
  { id: "hero", coverage: "front_back" },
  { id: "hero_side_fixture", coverage: "front_back_side" },
];

export const MOCK_RUNS: Run[] = [
  { id: "run_001", preset: "pull_hat_back", asset: "hero_side_fixture" },
  { id: "run_002", preset: "thicken_torso", asset: "hero" },
  { id: "run_003", preset: "widen_side_profile", asset: "hero_side_fixture" },
];

export interface EmbodimentParams {
  z_center_offset: number;
  thickness_scale: number;
  front_bias: number;
  back_bias: number;
  side_width_scale: number;
  taper_strength: number;
}

export const DEFAULT_EMBODIMENT: EmbodimentParams = {
  z_center_offset: 0.0,
  thickness_scale: 1.0,
  front_bias: 0.5,
  back_bias: 0.5,
  side_width_scale: 1.0,
  taper_strength: 0.2,
};

export interface Validation {
  validation_passed: boolean;
  mesh_connected_components: number;
  degenerate_faces: number;
  non_manifold_edges: number;
}

export const MOCK_VALIDATION: Validation = {
  validation_passed: true,
  mesh_connected_components: 1,
  degenerate_faces: 0,
  non_manifold_edges: 2,
};

export const MOCK_DIFF = {
  helpful: [
    { name: "hat_asymmetry", delta: +0.7 },
    { name: "directional_readability", delta: +0.04 },
  ],
  harmful: [
    { name: "side_projection_iou", delta: -0.003 },
    { name: "non_manifold", delta: +1 },
  ],
  skipped: ["equipment/shield/sword"],
};