from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApplyPresetRequest(BaseModel):
    asset_id: str
    base_params: str
    preset_profile: str
    preset_id: str
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    run_diff: bool = False
    fast_smoke: bool = False


class RunDiffRequest(BaseModel):
    asset_id: str
    base_params: str
    edited_params: str
    label_base: str = "default"
    label_edited: str = "edited"
    fast_smoke: bool = False


class ViewCandidatesRequest(BaseModel):
    sheet_path: str
    asset_id: str
    max_candidates: int = Field(default=320, ge=1, le=1000)
    ai_rank: bool = False


class CreateAssetFromCandidatesRequest(BaseModel):
    asset_id: str
    candidate_run_dir: str
    selection_version: str = "view_selection_v1"
    mode: str = Field(default="strict", pattern="^(strict|prototype)$")
    selection: dict[str, int | None] = Field(default_factory=dict)
    source_coverage: dict[str, str] = Field(default_factory=dict)


class BuildAssetRequest(BaseModel):
    asset_id: str


class RenameAssetRequest(BaseModel):
    new_asset_id: str


class ApiResponse(BaseModel):
    ok: bool
    run_id: str | None = None
    out_dir: str | None = None
    edited_params_path: str | None = None
    preset_application_report: dict[str, Any] | None = None
    param_diff_report: dict[str, Any] | None = None
    summary_md: str | None = None
    paths: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
