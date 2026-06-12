import type {
  DiffSummaryData,
  EmbodimentParameters,
  BuildJob,
  PresetOption,
  RawSheet,
  RunHistoryItem,
  StudioAsset,
  ValidationData
} from "../types/studio";

export const mockAssets: StudioAsset[] = [
  {
    id: "hero",
    coverage: "front_back",
    sprites: {
      front: "/placeholders/front.svg",
      back: "/placeholders/back.svg",
      side: "/placeholders/side.svg"
    }
  },
  {
    id: "hero_side_fixture",
    coverage: "front_back_side",
    sprites: {
      front: "/placeholders/front.svg",
      back: "/placeholders/back.svg",
      side: "/placeholders/side.svg"
    }
  }
];

export const mockPresets: PresetOption[] = [
  {
    id: "pull_hat_back",
    displayName: "pull_hat_back",
    description: "Increase rear hat extension and reduce front protrusion."
  },
  {
    id: "thicken_torso",
    displayName: "thicken_torso",
    description: "Add torso volume while preserving silhouette."
  },
  {
    id: "push_face_forward",
    displayName: "push_face_forward",
    description: "Bias the face region toward the front projection."
  },
  {
    id: "widen_side_profile",
    displayName: "widen_side_profile",
    description: "Increase side width for stronger lateral readability."
  }
];

export const defaultEmbodimentParams: EmbodimentParameters = {
  z_center_offset: 0,
  thickness_scale: 1,
  front_bias: 0.5,
  back_bias: 0.5,
  side_width_scale: 1,
  taper_strength: 0.25
};

export const mockDiffSummary: DiffSummaryData = {
  helpful: ["hat_asymmetry +0.7", "directional_readability +0.04"],
  harmful: ["side_projection_iou -0.003", "non_manifold +1"],
  skipped: ["equipment/shield/sword: part_not_present"]
};

export const mockValidation: ValidationData = {
  status: "PASS",
  metrics: [
    { key: "mesh_connected_components", value: 1, status: "PASS" },
    { key: "degenerate_faces", value: 0, status: "PASS" },
    { key: "non_manifold_edges", value: 7, status: "WARNING" },
    { key: "validation_passed", value: true, status: "PASS" }
  ]
};

export const mockRuns: RunHistoryItem[] = [
  {
    id: "run_001",
    preset: "pull_hat_back",
    asset: "hero_side_fixture"
  }
];

export const mockBuildJobs: BuildJob[] = [
  {
    job_id: "build_mock_001",
    asset_id: "hero_side_fixture",
    status: "completed",
    created_at: "2026-05-31T00:00:00Z",
    output_dir: "outputs/studio_builds/build_mock_001",
    validation_passed: true,
    validation_report: {
      passed: true,
      mesh_connected_components: 1,
      degenerate_face_count: 0,
      non_manifold_after_cleanup: 0,
      semantic_label_preservation_passed: true
    },
    artifacts: {
      validation_report: "outputs/studio_builds/build_mock_001/validation_report.json",
      manifest: "outputs/studio_builds/build_mock_001/manifest.json"
    }
  }
];

export const mockRawSheets: RawSheet[] = [
  {
    sheet_id: "mock_mario_sheet.png",
    filename: "SNES - Super Mario World - Playable Characters - Mario.png",
    path: "assets/raw/SNES - Super Mario World - Playable Characters - Mario.png",
    width: 405,
    height: 2464,
    size_bytes: 279728
  }
];
