from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from studio_api.models import ApiResponse, ApplyPresetRequest, BuildAssetRequest, CreateAssetFromCandidatesRequest, RenameAssetRequest, RunDiffRequest, ViewCandidatesRequest
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
    allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
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


@app.patch("/assets/{asset_id}")
def rename_asset(asset_id: str, request: RenameAssetRequest) -> dict:
    try:
        return services.rename_asset_service(asset_id, request.new_asset_id)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict:
    try:
        return services.delete_asset_service(asset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/assets/{asset_id}/delete")
def delete_asset_fallback(asset_id: str) -> dict:
    return delete_asset(asset_id)


@app.get("/raw-sheets")
def list_raw_sheets() -> dict:
    return {"ok": True, "sheets": services.list_raw_sheets()}


@app.post("/raw-sheets/upload")
async def upload_raw_sheet(request: Request, filename: str = Query(..., min_length=1)) -> dict:
    try:
        return services.upload_raw_sheet_service(filename, await request.body())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/file")
def serve_file(path: str = Query(..., min_length=1)) -> FileResponse:
    try:
        return FileResponse(services.file_response_path(path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {path}") from exc
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


@app.post("/view-candidates")
def extract_view_candidates(request: ViewCandidatesRequest) -> dict:
    try:
        return services.extract_view_candidates_service(
            request.sheet_path,
            request.asset_id,
            request.max_candidates,
            request.ai_rank,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/assets/from-candidates")
def create_asset_from_candidates(request: CreateAssetFromCandidatesRequest) -> dict:
    try:
        return services.create_asset_from_candidates_service(
            request.asset_id,
            request.candidate_run_dir,
            request.selection_version,
            request.mode,
            request.selection,
            request.source_coverage,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/build-asset")
def start_build_asset_job(request: BuildAssetRequest) -> dict:
    try:
        return services.start_build_asset_job_service(request.asset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs")
def list_jobs() -> dict:
    return {"ok": True, "jobs": services.list_build_jobs()}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return {"ok": True, "job": services.get_build_job(job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc
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
