# Phase 9F.1 Manual E2E Mesh Debug Handoff

## Status

Phase 9F.1 is functionally verified for the mesh viewer path.

The live Studio can select a completed build and render the real geometry from the build output instead of the placeholder cube.

Verified build:

```text
build_20260601T143749190120Z_mario
```

## Issue Found

The viewer was looking only for:

```text
mesh_topology_cleaned
mesh
```

The current real builder does not emit `mesh.json` or `mesh_topology_cleaned.json` for the tested `mario` build. It emits renderable geometry inside:

```text
outputs/studio_builds/build_20260601T143749190120Z_mario/topological_model.json
```

That file contains:

```text
schema: spritespatial_topological_model_v1
vertices: 6528
indices: 9792
triangles: 3264
colors: 6528
```

## Root Cause

This was an integration mismatch, not a reconstruction bug.

The backend exposed `topological_model`, but the frontend mesh viewer did not treat it as a renderable mesh artifact. The frontend parser also required `faces`, while the real artifact uses flat `indices`.

There was a second integration issue: `/jobs` returned lightweight job summaries without artifact metadata, so a selected completed run could initially have no mesh paths until `/jobs/{job_id}` was fetched.

## Files Changed

```text
studio/src/components/MeshViewer.tsx
studio/src/lib/buildMeshGeometry.ts
studio/src/lib/buildMeshGeometry.test.ts
studio/src/components/MeshViewer.test.tsx
studio_api/services.py
test_studio_api.py
requirements.txt
```

Generated verification artifacts:

```text
outputs/studio_api/manual_smoke/phase9f1_api_check.json
outputs/studio_api/manual_smoke/phase9f1_artifact_listing.json
outputs/studio_api/manual_smoke/phase9f1_mesh_fetch_check.json
docs/handoffs/phase9f1_mesh_viewer_solid.png
docs/handoffs/phase9f1_mesh_viewer_wireframe.png
docs/handoffs/phase9f1_mesh_viewer_vertex_color.png
docs/handoffs/phase9f1_mesh_viewer_error_or_unavailable.png
```

## Fixes Made

- MeshViewer now treats `topological_model` as the preferred renderable artifact.
- MeshViewer displays artifact key, artifact path, fetch status, parse status, vertex count, face count, current mode, and error message.
- MeshViewer no longer silently looks normal when a completed run has a mesh-like artifact but parsing fails.
- Geometry is centered and scaled to fit the viewer.
- Parser now supports:
  - `vertices`
  - `verts`
  - nested `mesh.vertices`
  - `faces`
  - `triangles`
  - flat `indices`
  - quad triangulation
  - `{x,y,z}` vertex objects
  - optional vertex colors
- `/jobs` now includes artifacts and validation fields from job records.
- Job reads hydrate artifact metadata from the output folder when possible.
- Added `httpx2` so `test_studio_api.py` actually runs instead of skipping all API tests.

## Backend Checks

Manual API checks performed against:

```text
http://127.0.0.1:8787
```

Checked:

```text
GET /health
GET /assets
GET /raw-sheets
GET /jobs
GET /jobs/build_20260601T143749190120Z_mario
GET /file?path=outputs/studio_builds/build_20260601T143749190120Z_mario/topological_model.json
```

Result:

```text
/file returned JSON successfully.
topological_model.json exists on disk.
/jobs includes artifact metadata.
```

## Frontend Checks

Manual browser smoke was performed in LIVE mode.

Confirmed:

```text
LIVE mode connected
asset list loaded
raw sheet loaded
build history loaded
completed mario build selected
real mesh appeared
solid mode worked
wireframe mode worked
vertex color mode worked
unavailable/error state captured
```

## Screenshots

```text
docs/handoffs/phase9f1_mesh_viewer_solid.png
docs/handoffs/phase9f1_mesh_viewer_wireframe.png
docs/handoffs/phase9f1_mesh_viewer_vertex_color.png
docs/handoffs/phase9f1_mesh_viewer_error_or_unavailable.png
```

## Validation Results

Passed:

```text
.\.venv\Scripts\python.exe tools\validate_project.py --skip-godot
.\.venv\Scripts\python.exe -m unittest test_studio_api.py
.\.venv\Scripts\python.exe -m unittest test_build_topological_sprite_model.py
cd studio
npm test
npm run build
```

Notes:

```text
test_studio_api.py: 11 tests ran, 11 passed.
npm test: 13 files passed, 32 tests passed.
npm run build: passed with the known Vite chunk-size warning from the Three.js bundle.
```

## Commands Deliberately Not Run

```text
Godot scene load was not run.
No reconstruction, SDF, morphology, meshing, ML, or Godot integration code was changed.
```

## Caveats

- The current real builder emits renderable geometry as `topological_model.json`, not `mesh.json`.
- `validation_report.json` for the latest real `mario` Studio build exists but contains `null`, so the build panel validation can show pending even though the command completed and emitted geometry.
- Automated backend tests create mocked build records with empty JSON artifacts. A real `mario` build was launched after tests so the newest completed run used for screenshots was a real build.
- The selected asset label in the top bar can remain visually stale while the selected build run is `mario`; this did not block mesh loading but should be cleaned up in the Studio state flow.

## Recommended Next Phase

Phase 10A should proceed with the end-to-end Studio asset pipeline:

```text
Raw Sheet
Extract Candidates
Assign Views
Create Asset
Build
View Mesh
```

Keep reconstruction quality work parked until the workflow is smooth without filesystem or command-line interaction.
