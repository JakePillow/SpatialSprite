# Phase 10A Authoritative View Selection Handoff

Date: 2026-06-06

## Status

Phase 10A is implemented and manually smoke-tested through Studio.

The completed workflow is:

```text
Raw Sheet
-> Extract Candidates
-> Assign FRONT / SIDE / BACK
-> Create Asset
-> Persist view_selection_v1
```

No reconstruction, SDF, meshing, Godot, or ML changes were made for this phase.

## Product Contract

Studio now creates assets from an explicit authoritative view selection payload:

```json
{
  "selection_version": "view_selection_v1",
  "mode": "strict",
  "selection": {
    "front": 0,
    "side": 1,
    "back": 2
  }
}
```

Strict mode requires `front`, `side`, and `back`.

Prototype mode requires `front` only and emits warnings for inferred `side` or `back`.

The generated asset writes:

- `front.png`
- `side.png`
- `back.png`
- `view_selection_v1.json`
- `spriteasset_v1.json`
- default embodiment params
- blank semantic override PNGs

`spriteasset_v1.json` maps side authority into the existing builder contract:

```json
"source_sprites": {
  "front": "front.png",
  "back": "back.png",
  "left": "side.png",
  "right": "side.png"
}
```

## Backend

Implemented in:

- `studio_api/models.py`
- `studio_api/main.py`
- `studio_api/services.py`
- `test_studio_api.py`

Backend behavior:

- accepts `selection_version`, `mode`, and `selection`
- rejects non-`view_selection_v1`
- rejects invalid mode
- validates candidate IDs against `candidate_report.json`
- rejects candidate image paths outside the run `candidates/` directory
- rejects unsafe asset IDs and duplicate assets
- warns on duplicate candidate reuse
- warns when side appears front-like
- allows prototype front-only assets while preserving a machine-readable warning trail

## Studio UI

Implemented in:

- `studio/src/hooks/useStudioState.ts`
- `studio/src/pages/Studio.tsx`
- `studio/src/components/CandidateGrid.tsx`
- `studio/src/components/ViewAssignmentPanel.tsx`
- `studio/src/components/AssetCreationPanel.tsx`
- `studio/src/types/studio.ts`
- `studio/src/api/assets.ts`

UI behavior:

- candidate cards show visible `id N`
- candidate cards show FRONT/SIDE/BACK assignment badges
- clicking a candidate assigns it to the active role
- active role advances `front -> side -> back`
- manual role buttons remain available
- keyboard shortcuts:
  - `F` assign selected candidate to front
  - `S` assign selected candidate to side
  - `B` assign selected candidate to back
  - `R` reset current role
- strict/prototype mode is visible in Create Asset
- strict mode disables create until FRONT/SIDE/BACK are assigned
- prototype mode allows FRONT-only creation with warnings
- candidate extraction uses the pending new asset id when it is valid, so raw-sheet candidate runs are namespaced under the authored asset instead of the previously selected sample asset

## Manual Smoke

Smoke ran through real Studio UI at `http://127.0.0.1:5173` against API `http://127.0.0.1:8787`.

Input sheet:

```text
assets/raw/SNES - Super Mario World - Playable Characters - Mario.png
```

Created asset:

```text
assets/samples/phase10a_mario_manual_1780756814187
```

Selected candidates:

```text
front = 0
side  = 1
back  = 2
```

Generated selection file:

```text
assets/samples/phase10a_mario_manual_1780756814187/view_selection_v1.json
```

The selection file confirms the candidate run is under the new authored asset:

```text
outputs/phase10a_mario_manual_1780756814187/view_candidates/20260606T144017Z_phase10a_mario_manual_1780756814187_sheet_candidates
```

Expected warning from the heuristic:

```text
Side may be front-like. Confirm manually.
```

## Screenshots

- `docs/handoffs/phase10a_candidate_grid_with_ids.png`
- `docs/handoffs/phase10a_front_selected.png`
- `docs/handoffs/phase10a_side_selected.png`
- `docs/handoffs/phase10a_back_selected.png`
- `docs/handoffs/phase10a_create_authoritative_asset.png`

## Validation

Passed:

```powershell
.\.venv\Scripts\python.exe tools\validate_project.py --skip-godot
.\.venv\Scripts\python.exe -m unittest test_studio_api.py
.\.venv\Scripts\python.exe -m unittest test_build_topological_sprite_model.py
cd studio
npm test
npm run build
```

Results:

- `test_studio_api.py`: 18 passed
- `test_build_topological_sprite_model.py`: 12 passed
- Studio Vitest: 13 files, 34 tests passed
- Studio production build passed
- `validate_project.py --skip-godot` passed Python compile, schema validation, sample profiled build, validation report check, manifest check

## Caveats

- The heuristic can detect suspicious selections, but it does not know true semantic pose. Human review is still authoritative.
- The builder still expects left/right directional source names, so Phase 10A maps the single `side.png` into both left and right.
- Prototype mode copies front into missing side/back files for builder compatibility, while `view_selection_v1.json` records those views as inferred.
- Vite reports the existing large bundle warning during production build. This is not new Phase 10A behavior.

## Next Recommended Step

Proceed to the end-to-end build/view part of the product workflow:

```text
Created Asset
-> Build Asset
-> Select Build Run
-> Mesh loads
-> Mesh rotates
-> Render mode toggles work
```

Do that with `hero`, `hero_side_fixture`, and a Mario-derived Studio asset before returning to reconstruction quality work.
