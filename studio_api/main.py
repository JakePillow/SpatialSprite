from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from studio_api.models import ApiResponse, ApplyPresetRequest, RunDiffRequest
from studio_api import services


app = FastAPI(
    title="SpriteSpatial Studio API",
    version="0.1.0",
    description="Minimal local-only API for SpriteSpatial preset and parameter-diff workflows.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return services.health()


@app.get("/assets")
def list_assets() -> dict:
    return {"ok": True, "assets": services.list_assets()}


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    try:
        return {"ok": True, "asset": services.get_asset(asset_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/presets")
def list_presets() -> dict:
    return {"ok": True, "profiles": services.list_preset_profiles()}


@app.get("/presets/{profile_id}")
def get_preset_profile(profile_id: str) -> dict:
    try:
        return {"ok": True, "profile": services.get_preset_profile(profile_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Preset profile not found: {profile_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/apply-preset", response_model=ApiResponse)
def apply_preset(request: ApplyPresetRequest) -> ApiResponse:
    try:
        return ApiResponse(
            **services.apply_preset_service(
                request.asset_id,
                request.base_params,
                request.preset_profile,
                request.preset_id,
                request.intensity,
                request.run_diff,
                fast_smoke=request.fast_smoke,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/run-diff", response_model=ApiResponse)
def run_diff(request: RunDiffRequest) -> ApiResponse:
    try:
        result = services.run_diff_service(
            request.asset_id,
            request.base_params,
            request.edited_params,
            request.label_base,
            request.label_edited,
            fast_smoke=request.fast_smoke,
        )
        return ApiResponse(
            ok=bool(result.get("ok", False)),
            run_id=result.get("run_id"),
            out_dir=result.get("out_dir"),
            param_diff_report=result.get("param_diff_report"),
            summary_md=result.get("summary_md"),
            paths=result.get("paths", {}),
            error=result.get("error"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs")
def list_runs() -> dict:
    return {"ok": True, "runs": services.list_runs()}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return {"ok": True, "run": services.get_run(run_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
