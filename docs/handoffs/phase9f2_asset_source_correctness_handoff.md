# Phase 9F.2 Asset Source Correctness Handoff

## Status

Phase 9F.2 is complete.

A fresh Studio/API-created asset was generated and built:

```text
asset_id: mario_clean_test
build: build_20260601T151425080157Z_mario_clean_test
```

The created `front.png` is the selected candidate crop, not the raw sheet or contact sheet.

## Root Cause

The audit did not find the checked-in `assets/samples/mario` pointing at the raw sprite sheet. It points to local 24x32 crop files:

```text
mario_front.png
mario_back.png
mario_left.png
mario_right.png
```

However, the Studio asset creation contract was too permissive:

- candidate IDs could fall back to filename guesses instead of requiring metadata
- candidate record paths were only constrained to the candidate run directory, not specifically `candidates/`
- created assets did not record candidate selection provenance
- Studio builds did not guard against accidentally building from a full-sheet-sized front image

So the observed “wrong sheet/spire” failure was not proven to be an active off-by-one in the current UI, but the integration layer was not strict enough to prevent or diagnose that class of source mistake.

## Files Changed

```text
studio_api/services.py
test_studio_api.py
studio/src/api/client.test.ts
```

Generated audit/proof files:

```text
outputs/studio_api/manual_smoke/phase9f2_mario_asset_source_audit.json
outputs/studio_api/manual_smoke/phase9f2_mario_asset_sources.png
outputs/studio_api/manual_smoke/phase9f2_candidate_selection_contact_sheet.png
outputs/studio_api/manual_smoke/phase9f2_mario_clean_asset_sources.png
outputs/studio_api/manual_smoke/phase9f2_mario_clean_build_summary.json
```

Required handoff screenshots:

```text
docs/handoffs/phase9f2_wrong_asset_source_before.png
docs/handoffs/phase9f2_correct_candidate_assignment.png
docs/handoffs/phase9f2_correct_asset_sources.png
docs/handoffs/phase9f2_clean_mesh_viewer.png
```

## Candidate ID Contract

Canonical contract now enforced:

```json
{
  "candidate_id": 0,
  "path": "outputs/.../candidates/candidate_000.png",
  "bbox": [74, 48, 95, 75],
  "size": [40, 48]
}
```

Selection payload:

```json
{
  "front": 0,
  "back": 1,
  "left": 2,
  "right": 3
}
```

Backend behavior:

- resolves selected views by `candidate_id` through `candidate_report.json`
- rejects missing candidate IDs
- rejects candidate paths outside the run’s `candidates/` directory
- copies the crop into `assets/samples/<asset_id>/<view>.png`
- writes `spriteasset_v1.json` with local sprite references
- records `candidate_selection` metadata in the asset JSON

## Clean Asset Proof

Created:

```text
assets/samples/mario_clean_test/
```

`spriteasset_v1.json` references:

```json
{
  "front": "front.png",
  "back": "back.png",
  "left": "left.png",
  "right": "right.png"
}
```

Source proof:

```text
front.png size: 40x48
front candidate_id: 0
front crop sha256 == selected candidate sha256: true
references raw sheet: false
```

Build proof:

```text
mesh schema: spritespatial_topological_model_v1
vertices: 4816
triangles: 2408
colors: 4816
```

## Build Guard

Studio build orchestration now rejects obvious full-sheet sources before launching the builder:

```text
Front sprite appears to be a full sheet or invalid crop.
```

Current threshold:

```text
front width > 256 or front height > 256
```

This guard lives in Studio API orchestration only. No core reconstruction code was changed.

## Validation

Passed:

```text
.\.venv\Scripts\python.exe tools\validate_project.py --skip-godot
.\.venv\Scripts\python.exe -m unittest test_studio_api.py
.\.venv\Scripts\python.exe -m unittest test_build_topological_sprite_model.py
cd studio
npm test
npm run build
```

Results:

```text
test_studio_api.py: 15 tests passed
test_build_topological_sprite_model.py: 12 tests passed
npm test: 13 files, 33 tests passed
npm run build: passed with known Three.js chunk-size warning
```

## Manual Smoke

Confirmed:

```text
LIVE mode
raw sheet loads
candidate crops exist
candidate IDs are visible/traceable
mario_clean_test created from selected candidates
front.png visually correct crop
front.png byte-identical to selected candidate crop
build completed
mesh viewer rendered topological_model geometry
```

## Caveats

- The top status bar can still show a stale selected asset label while the selected build run is different. The mesh viewer itself used the selected `mario_clean_test` build run.
- `validation_report.json` for the clean build exists but is `null`, so validation can display pending even when the build completes and emits geometry.
- The generated mesh is still low quality; this phase only proves correct source plumbing.

## Recommended Next Phase

Proceed to Phase 10A: finish the end-to-end Studio workflow with zero filesystem interaction.

Do not return to reconstruction quality work until asset creation, build selection, validation display, and mesh viewing are boringly reliable.
