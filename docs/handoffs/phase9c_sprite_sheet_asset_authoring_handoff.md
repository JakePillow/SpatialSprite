# SpriteSpatial Handoff: From Sprite Sheet to Proper Editable Asset

## Purpose

This handoff explains what needs to be built next so the local SpriteSpatial Studio can load a raw sprite sheet, extract/select views like the Link-style `hero` asset, create a proper authored asset folder, apply semantic/embodiment edits, and run the reconstruction pipeline from the editor.

The key point: the geometry pipeline is already powerful enough to use authored front/back/side views, but the Studio UI and Studio API do not yet expose the asset-authoring workflow. Right now the editor is mostly an asset/preset/diff shell.

## Current Status

Working pieces:

- `studio/` local Vite/React editor shell exists.
- `studio_api/` FastAPI backend exists.
- UI can list sample assets from `assets/samples/`.
- UI can list embodiment presets from `profiles/embodiment_presets/`.
- UI can call `/apply-preset` and show returned diff/validation-style data.
- Mock fallback exists when the backend is offline.
- Candidate extraction CLI exists:

```text
tools/find_view_candidates.py
```

- Existing sample assets:

```text
assets/samples/hero/
assets/samples/hero_side_fixture/
assets/samples/mario/
```

- Existing raw sheet folder currently contains:

```text
assets/raw/SNES - Super Mario World - Playable Characters - Mario.png
```

Important caveat:

The Link-like working asset is represented as `assets/samples/hero/` and `assets/samples/hero_side_fixture/`. I do not see a raw Link sprite sheet under `assets/raw/` at the moment. To author from a Link sheet in the editor, first place the raw Link sheet under `assets/raw/`.

## Current Limitations Blocking Proper Asset Creation

The Studio UI cannot yet:

- browse raw sprite sheets in `assets/raw/`
- display a real source sheet image
- run `tools/find_view_candidates.py`
- show candidate crops in an assignable grid
- let the user choose front/back/left/right from candidates
- create a new `assets/samples/<asset_id>/` folder
- write `spriteasset_v1.json`
- write/copy selected source sprites
- create or edit semantic override masks
- show real source sprites instead of placeholders
- launch a full reconstruction build from the browser
- preview generated `mesh.json`

The Studio API cannot yet:

- list raw sheets
- serve whitelisted asset/output image files to the frontend
- create assets from selected candidates
- expose view-candidate extraction as an endpoint
- persist candidate selections
- expose semantic masks as editable resources
- run full asset builds as jobs
- stream logs/status for long builds
- return real mesh/capture artifacts for viewer use

## Existing Manual CLI Flow

Today, the closest manual flow for a sheet is:

```powershell
cd C:\dev\SpatialSprite

python tools\find_view_candidates.py ^
  --asset assets\samples\mario\spriteasset_v1.json ^
  --sheet "assets\raw\SNES - Super Mario World - Playable Characters - Mario.png" ^
  --out outputs\mario\view_candidates
```

Optional AI ranking:

```powershell
python tools\find_view_candidates.py ^
  --asset assets\samples\mario\spriteasset_v1.json ^
  --sheet "assets\raw\SNES - Super Mario World - Playable Characters - Mario.png" ^
  --ai-rank ^
  --out outputs\mario\view_candidates_ai
```

Do not rely on `--confirm-copy` as the editor default. The proper workflow should require explicit user confirmation per selected view before writing source sprites.

## Target Editor Workflow

The next usable Studio workflow should be:

1. Open Studio.
2. Choose `New Asset From Sheet`.
3. Select a raw sprite sheet from `assets/raw/`.
4. Run candidate extraction.
5. Review candidate contact sheet/crops.
6. Assign:

```text
front
back
left
right
```

7. Confirm source coverage:

```text
front: authored
back: authored | missing
left/right: authored_side | placeholder | missing
```

8. Save as:

```text
assets/samples/<asset_id>/
```

9. Generate:

```text
spriteasset_v1.json
front.png
back.png
left.png
right.png
semantic_overrides/
embodiment_params_default.json
embodiment_params.json
```

10. Run validation/build.
11. Apply embodiment presets.
12. Inspect diff/validation.
13. Preview generated mesh/captures when Phase 9C/9D exposes them.

## Required Backend Work

Add endpoints to `studio_api/main.py` and service functions to `studio_api/services.py`.

### 1. Raw Sheet Listing

Endpoint:

```text
GET /raw-sheets
```

Return:

```json
{
  "ok": true,
  "sheets": [
    {
      "sheet_id": "SNES - Super Mario World - Playable Characters - Mario.png",
      "path": "assets/raw/SNES - Super Mario World - Playable Characters - Mario.png",
      "width": 405,
      "height": 2464
    }
  ]
}
```

Rules:

- Only list files under `assets/raw/`.
- Allow `.png` initially.
- No arbitrary absolute paths.

### 2. Safe File/Image Serving

The frontend needs to display images from `assets/raw/`, `assets/samples/`, and selected `outputs/` folders.

Preferred endpoint:

```text
GET /file?path=<relative_path>
```

Rules:

- Path must be relative.
- Resolve only under allowed roots:

```text
assets/raw/
assets/samples/
outputs/
```

- Reject `..`, absolute paths, and non-image files unless explicitly allowed.
- Return `FileResponse`.

Alternative:

Mount static routes:

```text
/assets/raw-static
/assets/samples-static
/outputs-static
```

But a guarded `/file` endpoint is easier to keep safe.

### 3. Candidate Extraction Endpoint

Endpoint:

```text
POST /view-candidates
```

Request:

```json
{
  "sheet_path": "assets/raw/link_sheet.png",
  "asset_id": "link_test",
  "max_candidates": 320,
  "ai_rank": false
}
```

Response:

```json
{
  "ok": true,
  "run_id": "view_candidates_link_test_...",
  "out_dir": "outputs/link_test/view_candidates/...",
  "candidate_report": {},
  "candidate_contact_sheet": "outputs/link_test/view_candidates/candidate_contact_sheet.png",
  "candidates": [
    {
      "candidate_id": 0,
      "path": "outputs/link_test/view_candidates/candidates/candidate_000.png",
      "bbox": [0, 0, 32, 32],
      "alpha_coverage": 0.32
    }
  ]
}
```

Implementation options:

- Best: refactor `tools/find_view_candidates.py` into importable service functions.
- Acceptable first step: call the CLI with `subprocess.run`, then parse `candidate_report.json`.

Do not call AI ranking by default. If `ai_rank` is added to the UI, keep it advisory only.

### 4. Candidate Selection Endpoint

Endpoint:

```text
POST /assets/from-candidates
```

Request:

```json
{
  "asset_id": "link_test",
  "candidate_run_dir": "outputs/link_test/view_candidates/...",
  "selection": {
    "front": 12,
    "back": 55,
    "left": 42,
    "right": 43
  },
  "source_coverage": {
    "front": "authored",
    "back": "authored",
    "left": "authored_side",
    "right": "authored_side"
  }
}
```

Output files:

```text
assets/samples/link_test/front.png
assets/samples/link_test/back.png
assets/samples/link_test/left.png
assets/samples/link_test/right.png
assets/samples/link_test/spriteasset_v1.json
assets/samples/link_test/embodiment_params_default.json
assets/samples/link_test/embodiment_params.json
```

`spriteasset_v1.json` should follow the existing schema:

```json
{
  "schema_version": "spriteasset_v1",
  "asset_name": "link_test",
  "asset_type": "character",
  "source_sprites": {
    "front": "front.png",
    "back": "back.png",
    "left": "left.png",
    "right": "right.png"
  },
  "render_mode": "directional_sprite_3d",
  "pixel_scale": 0.06,
  "upscaling": {
    "method": "nearest_integer",
    "scale_factor": 2,
    "generates_new_art_content": false,
    "deterministic": true,
    "output_format": "png"
  },
  "collision": {
    "type": "capsule",
    "height": 1.6,
    "radius": 0.35
  },
  "source_coverage": {
    "front": "authored",
    "back": "authored",
    "left": "authored_side",
    "right": "authored_side",
    "candidate_selection_method": "manual_editor"
  }
}
```

### 5. Semantic Override Support

Minimum viable next step:

```text
POST /assets/{asset_id}/semantic-overrides/bootstrap
```

This creates empty/placeholder masks:

```text
semantic_overrides/
  head.png
  face.png
  hat_hair.png
  torso.png
  left_arm.png
  right_arm.png
  left_leg.png
  right_leg.png
  boots_feet.png
  equipment.png
  outline.png
```

Better step:

- Add a simple mask editor in the UI later.
- For now, expose existing masks and allow upload/replace of PNG masks.

Important:

For Link-like assets, `hat_hair` must be clean for directional morphology. The current geometry quality depends heavily on this.

### 6. Full Build Endpoint

Endpoint:

```text
POST /build-asset
```

Request:

```json
{
  "asset_id": "link_test",
  "profile": "prototype_32",
  "pipeline": "editor_safe_qef",
  "embodiment_params": "assets/samples/link_test/embodiment_params.json"
}
```

Internally run the current strongest editor-safe command:

```powershell
python tools\build_topological_sprite_model.py ^
  --asset assets\samples\<asset_id>\spriteasset_v1.json ^
  --profile profiles\prototype_32.json ^
  --semantic-overrides assets\samples\<asset_id>\semantic_overrides ^
  --semantic-override-mode supplement ^
  --semantic-parts ^
  --semantic-depth-profiles ^
  --semantic-depth-profile humanoid_voxel ^
  --directional-morphology ^
  --morphology-profile fantasy_humanoid ^
  --embodiment-params assets\samples\<asset_id>\embodiment_params.json ^
  --depth-mode mylar_edt ^
  --closed-body ^
  --back-mode front_back_sprite ^
  --multi-view-authority ^
  --view-authority-mode front_back_side ^
  --constraint-arbitration ^
  --mesh-backend surface_nets_patch ^
  --patch-profile humanoid_voxel ^
  --macro-patches ^
  --macro-patch-profile humanoid_voxel ^
  --adaptive-sdf-resolution ^
  --resolution-profile prototype_adaptive ^
  --surface-net-vertex-placement patch_qef ^
  --qef-regularization 0.001 ^
  --qef-max-displacement 0.35 ^
  --topology-cleanup ^
  --surface-net-smoothing-alpha 0.65 ^
  --preserve-silhouette-edges ^
  --render-profile voxel_sprite ^
  --out outputs\<asset_id>\studio_build
```

This should probably be a background job rather than a blocking request.

### 7. Job System

Add a tiny job registry:

```text
POST /jobs/build-asset
GET /jobs
GET /jobs/{job_id}
```

Track:

```json
{
  "job_id": "...",
  "kind": "build_asset",
  "status": "queued|running|succeeded|failed",
  "created_at": "...",
  "finished_at": "...",
  "stdout_tail": "",
  "stderr_tail": "",
  "out_dir": "",
  "validation_report": {}
}
```

This matters because full builds and diffs can be slow.

## Required Frontend Work

Add new UI areas under `studio/src/`.

### 1. Source Sheet Browser

New components:

```text
studio/src/components/SourceSheetBrowser.tsx
studio/src/components/SourceSheetPreview.tsx
```

API wrappers:

```text
studio/src/api/sheets.ts
```

Flow:

- call `GET /raw-sheets`
- show sheet list
- show selected sheet image via safe file endpoint
- button: `Extract Candidates`

### 2. Candidate Review Grid

New components:

```text
studio/src/components/CandidateGrid.tsx
studio/src/components/ViewAssignmentPanel.tsx
```

Features:

- display candidate images
- filter by AI/deterministic ranking if present
- click candidate
- assign to front/back/left/right
- show selected four views
- warn if back or side missing
- warn if side is likely placeholder/mirrored

### 3. Asset Creation Panel

New component:

```text
studio/src/components/AssetCreationPanel.tsx
```

Fields:

```text
asset_id
asset_type
pixel_scale
front candidate
back candidate
left candidate
right candidate
source coverage labels
```

Button:

```text
Create Asset
```

Calls:

```text
POST /assets/from-candidates
```

### 4. Real Sprite Display

Currently `studio/src/hooks/useStudioState.ts` uses placeholder images:

```ts
const PLACEHOLDER_SPRITES = {
  front: "/placeholders/front.svg",
  back: "/placeholders/back.svg",
  side: "/placeholders/side.svg"
};
```

Replace this in live mode with URLs from the backend safe file endpoint:

```text
/file?path=assets/samples/<asset_id>/<sprite_filename>
```

Keep placeholders only for mock mode or missing sprites.

### 5. Semantic Information Panel

The existing API already returns:

```text
semantic_override_labels
available_params_files
```

Expose this in the UI:

- label list
- nonempty badge
- missing required labels warning
- `hat_hair` quality warning for Link-like assets

### 6. Build/Validation Panel

Add:

```text
Build Asset button
Job status display
validation_report.json parser
mesh/capture artifact links
```

Do not run Godot from the editor yet unless explicitly requested. Use `--skip-godot` validation and mesh/debug artifacts first.

### 7. Mesh Preview Integration

Phase 9B still uses a placeholder cube.

Next steps:

- expose generated `mesh.json` path from build output
- add API file endpoint for `mesh.json`
- load mesh JSON in Three.js
- render semantic materials client-side

Do this after asset creation/build workflow works. Do not block sprite sheet authoring on mesh rendering.

## Proper Link-like Asset Requirements

For a proper Link-style asset, the asset must have:

```text
front authored sprite
back authored sprite
left or right authored side sprite
semantic_overrides/ with clean masks
especially hat_hair.png
embodiment_params_default.json
embodiment_params.json
source_coverage marking real view authority
```

Minimum semantic labels:

```text
outline
head
face
hat_hair
torso
left_arm
right_arm
left_leg
right_leg
boots_feet
```

Optional:

```text
equipment
```

If no true side sprite exists:

- do not claim full authored side authority
- mark side as `missing`, `inferred`, or `placeholder`
- allow the build, but display fidelity warnings

If no true back sprite exists:

- `prototype_32` can fall back to semantic rules
- quality profiles should warn/fail depending policy
- editor should prompt user to provide/select a back sprite

## Suggested Phase Split

### Phase 9C: Sheet Browser + Candidate Review

Goal:

Use the editor to browse `assets/raw`, run `find_view_candidates`, and select front/back/side candidates.

Deliverables:

```text
GET /raw-sheets
GET /file
POST /view-candidates
SourceSheetBrowser
CandidateGrid
ViewAssignmentPanel
candidate review tests
```

Success:

The user can open the Mario or Link sheet in Studio and visually select front/back/left/right candidates.

### Phase 9D: Asset Creation

Goal:

Save selected candidates into a new `assets/samples/<asset_id>/` folder.

Deliverables:

```text
POST /assets/from-candidates
AssetCreationPanel
spriteasset_v1 writer
source_coverage writer
default embodiment params writer
semantic_overrides bootstrap
```

Success:

The editor creates a new asset folder and it appears in the Asset Browser without manual file editing.

### Phase 9E: Build Job Integration

Goal:

Run the current strongest editor-safe build pipeline from Studio.

Deliverables:

```text
POST /jobs/build-asset
GET /jobs/{job_id}
BuildPanel
ValidationReportPanel
artifact links
```

Success:

The user can click Build and see validation outputs for the created asset.

### Phase 9F: Real Mesh Preview

Goal:

Load generated `mesh.json` in Three.js.

Deliverables:

```text
mesh JSON file endpoint
mesh loader
semantic color material mapping
front/side/back camera controls
wireframe toggle
```

Success:

The editor previews the generated asset mesh instead of the placeholder cube.

### Phase 10A: Semantic Mask Authoring

Goal:

Make semantic override creation usable from the editor.

Deliverables:

```text
mask layer viewer
paint/fill tools or PNG upload
label visibility toggles
overlap validation
critical label coverage checks
```

Success:

The user can fix `hat_hair`, torso/head overlap, limbs, and outline authority without leaving Studio.

## Safety Rules for Implementation

Keep all API path handling strict:

- no absolute arbitrary input paths
- no `..`
- allowed roots only:

```text
assets/raw/
assets/samples/
outputs/
profiles/
```

- never overwrite source sprites unless user confirms
- never treat AI ranking as truth
- never generate art in this workflow
- always show view authority:

```text
authored
authored_side
placeholder
inferred
missing
```

## Validation Commands

Run from repo root:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_studio_api.py
python -m unittest test_build_topological_sprite_model.py
```

Run from frontend:

```powershell
cd C:\dev\SpatialSprite\studio
npm run test
npm run build
```

Manual local launch:

```powershell
# Terminal 1
cd C:\dev\SpatialSprite
python tools\run_studio_api.py --host 127.0.0.1 --port 8787

# Terminal 2
cd C:\dev\SpatialSprite\studio
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Definition of Done for "Proper Asset From Sheet"

A sprite sheet has been turned into a proper SpriteSpatial asset when:

- raw sheet is listed in Studio
- candidates are extracted
- front/back/side views are manually selected
- asset folder is created under `assets/samples/<asset_id>/`
- `spriteasset_v1.json` is valid
- source coverage is explicit
- semantic override masks exist
- `hat_hair` or equivalent directional parts are clean for Link-style sprites
- build command completes
- `validation_report.json` passes
- mesh is connected
- degenerate faces are zero
- semantic labels are preserved
- editor displays diff/validation output
- editor clearly labels missing/inferred/placeholder views

## Current Best Next Step

Implement Phase 9C:

```text
Raw Sheet Browser + Candidate Review
```

Do not start with mesh preview. The real bottleneck for making a proper asset is selecting authoritative source views from a sheet and saving them as a clean `spriteasset_v1` asset.
