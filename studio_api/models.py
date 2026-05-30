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
