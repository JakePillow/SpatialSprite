# SpriteSpatial Phase 8D Handoff: Minimal Local Editor API

## Status

Phase 8D is implemented and validated.

The repo now has a minimal local FastAPI backend that exposes the Phase 8C preset workflow and the Phase 8B parameter diff workflow without adding a frontend, Godot UI, ML, animation, rigging, new geometry, or new rendering.

## Added

API package:

```text
studio_api/__init__.py
studio_api/main.py
studio_api/models.py
studio_api/services.py
```

Launcher:

```text
tools/run_studio_api.py
```

Smoke test:

```text
test_studio_api.py
```

Dependency hints:

```text
requirements.txt
```

`fastapi` and `uvicorn` were added to requirements. `uvicorn` is imported only by the launcher so tests can run without starting a server.

## Launch Command

```powershell
python tools\run_studio_api.py --host 127.0.0.1 --port 8787
```

The launcher refuses non-local hosts in API v0.1.

## Endpoints

```text
GET  /health
GET  /assets
GET  /assets/{asset_id}
GET  /presets
GET  /presets/{profile_id}
POST /apply-preset
POST /run-diff
GET  /runs
GET  /runs/{run_id}
```

## API Behavior

The API is local-only and does not run Godot or the API visual judge.

It wraps existing functionality:

```text
tool/spritespatial/embodiment_presets.py
tools/run_embodiment_param_diff.py
tools/apply_embodiment_preset.py behavior
```

The service layer applies presets directly through Python functions. Full diff runs call the existing diff runner. Smoke tests use `fast_smoke` for `/run-diff` to avoid expensive reconstruction during unit tests.

## Path Safety

API v0.1 rejects arbitrary absolute paths.

Allowed roots:

```text
assets/samples/
profiles/embodiment_presets/
outputs/
```

Rules:

```text
asset_id must resolve under assets/samples/
preset_profile must resolve under profiles/embodiment_presets/
generated runs are written under outputs/studio_api/runs/
source assets are not mutated
```

## Smoke Test Output

```text
outputs/studio_api/smoke_test/api_smoke_report.json
```

Smoke checks:

```text
health endpoint
assets endpoint
presets endpoint
apply pull_hat_back preset
run fast-smoke diff
runs endpoint
run detail endpoint
```

## Example Apply Preset Payload

```json
{
  "asset_id": "hero_side_fixture",
  "base_params": "assets/samples/hero_side_fixture/embodiment_params_default.json",
  "preset_profile": "fantasy_humanoid",
  "preset_id": "pull_hat_back",
  "intensity": 0.75,
  "run_diff": true
}
```

Response includes:

```text
ok
run_id
out_dir
edited_params_path
preset_application_report
param_diff_report
summary_md
paths
```

## Example Run Diff Payload

```json
{
  "asset_id": "hero_side_fixture",
  "base_params": "assets/samples/hero_side_fixture/embodiment_params_default.json",
  "edited_params": "outputs/studio_api/runs/<run_id>/edited_params.json",
  "label_base": "default",
  "label_edited": "edited"
}
```

## Verification

Run:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
python -m unittest test_studio_api.py
```

All passed.

## Commands Deliberately Not Run

```text
Godot
API visual judge
frontend dev server
```

## Honest Caveats

The API is intentionally minimal. It is not yet a UI and does not manage long-running jobs asynchronously. A real frontend may want job status polling, cancellation, and streaming logs once full diffs are triggered from a browser.

`fast_smoke` is for tests only. It proves API routing, path safety, report writing, and run listing without performing reconstruction. Normal `/apply-preset` with `run_diff: true` invokes the existing parameter diff runner.

## Recommended Next Step

Add a tiny job registry around full diff runs before building a frontend. The first UI can then call `/apply-preset`, poll `/runs/{run_id}`, and show `param_diff_summary.md` plus the key JSON reports.
