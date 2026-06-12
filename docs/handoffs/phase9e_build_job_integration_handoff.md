# SpriteSpatial Phase 9E Handoff: Build Job Integration

## Status

Phase 9E is implemented and verified.

Studio can now:

- select an existing asset
- launch a build job from Studio
- poll job status until completion or failure
- display validation results from `validation_report.json`
- expose discovered build artifact links
- show build history sorted newest-first

This phase is orchestration-only: no reconstruction, mesh viewing, semantic painting, or Godot changes were made.

## Files Changed

- `studio_api/main.py`
- `studio_api/models.py`
- `studio_api/services.py`
- `studio/src/api/jobs.ts`
- `studio/src/api/studioApi.ts`
- `studio/src/hooks/useStudioState.ts`
- `studio/src/pages/Studio.tsx`
- `studio/src/components/BuildPanel.tsx`
- `studio/src/components/BuildPanel.test.tsx`
- `studio/src/components/BuildArtifactsPanel.tsx`
- `studio/src/components/RunHistory.tsx`
- `docs/handoffs/phase9e_build_job_integration_handoff.md`

## API Endpoints Added

POST `/jobs/build-asset`

Request:

```json
{
  "asset_id": "mario"
}
```

Response:

```json
{
  "ok": true,
  "job_id": "build_20260601_001",
  "status": "queued"
}
```

GET `/jobs`

Response:

```json
[
  {
    "job_id": "build_20260601_001",
    "asset_id": "hero",
    "status": "completed"
  }
]
```

GET `/jobs/{job_id}`

Response:

```json
{
  "job_id": "build_20260601_001",
  "asset_id": "hero",
  "status": "completed",
  "validation_report": {
    "passed": true,
    "mesh_connected_components": 1,
    "degenerate_face_count": 0
  },
  "artifacts": {
    "validation_report": "outputs/studio_builds/build_20260601_001/validation_report.json",
    "mesh": "outputs/studio_builds/build_20260601_001/mesh.json"
  }
}
```

## Backend Behavior

Build jobs are created in `outputs/studio_api/jobs/` and executed in a background thread.

The builder command is fixed to:

```text
python tools/build_topological_sprite_model.py --asset assets/samples/<asset_id>/spriteasset_v1.json --profile profiles/prototype_32.json --out outputs/studio_builds/<job_id>
```

Job states:

- `queued`
- `running`
- `completed`
- `failed`

When finished, the backend discovers known artifacts:

- `validation_report.json`
- `topological_model.json`
- `mesh.json`
- `mesh_topology_cleaned.json`
- `manifest.json`

The job detail also returns the parsed `validation_report`.

## Frontend Behavior

The Studio UI now includes:

- `BuildPanel` for launching builds
- `BuildArtifactsPanel` for artifact links
- `RunHistory` showing build jobs
- validation summary rendered from live job details

A build job is started with `POST /jobs/build-asset`, then Studio polls `GET /jobs/{job_id}` every 2 seconds until the job reaches `completed` or `failed`.

## Commands Run

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_studio_api.py
cd studio
npm test
npm run build
```

## Commands Not Run

- Godot
- API visual judge
- mesh viewer integration
- semantic painting
- full Studio dev server smoke test in browser

## Tests

Backend:

- `python -m unittest test_studio_api.py`

Frontend:

- `cd studio && npm test`

## Known Limitations

- Build job execution is asynchronous and background-threaded with no dedicated worker process.
- Artifact links open raw JSON in the browser; no special viewer is provided.
- Validation metrics are displayed only when present in the report.
- There is no mesh viewer or 3D preview in this phase.
- Build failures are surfaced, but there is no retry/queue management UI.

## Recommended Next Step

Phase 9F — Real Mesh Viewer

Load `mesh.json` and `mesh_topology_cleaned.json` into ThreeJS and replace the placeholder cube with a proper reconstructed mesh preview.
