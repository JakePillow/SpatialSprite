from __future__ import annotations

import json
import shutil
import subprocess
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


try:
    from fastapi.testclient import TestClient
    from studio_api.main import app
except Exception as exc:  # pragma: no cover - exercised only when optional dependency is absent
    TestClient = None
    app = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


WORKSPACE_ROOT = Path(__file__).resolve().parent
SMOKE_DIR = WORKSPACE_ROOT / "outputs" / "studio_api" / "smoke_test"
TEST_ASSET_IDS = (
    "studio_test_asset_9d",
    "studio_test_duplicate_9d",
    "studio_test_candidate_contract_9f2",
    "studio_test_full_sheet_guard_9f2",
    "studio_test_strict_success_10a",
    "studio_test_prototype_10a",
    "studio_test_rename_source_10c",
    "studio_test_renamed_10c",
    "studio_test_delete_action_10c",
)
TEST_RAW_SHEETS = (
    "studio_upload_sheet_10b.png",
)


@unittest.skipIf(TestClient is None, f"FastAPI test dependencies unavailable: {IMPORT_ERROR}")
class StudioApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        SMOKE_DIR.mkdir(parents=True, exist_ok=True)
        cls.report: dict[str, object] = {"schema": "spritespatial_studio_api_smoke_report_v1", "checks": []}

    @classmethod
    def tearDownClass(cls) -> None:
        for asset_id in TEST_ASSET_IDS:
            shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        for sheet_name in TEST_RAW_SHEETS:
            (WORKSPACE_ROOT / "assets" / "raw" / sheet_name).unlink(missing_ok=True)
        (SMOKE_DIR / "api_smoke_report.json").write_text(json.dumps(cls.report, indent=2) + "\n", encoding="utf-8")

    def _record(self, name: str, ok: bool, payload: object | None = None) -> None:
        self.report["checks"].append({"name": name, "ok": ok, "payload": payload})

    def _candidate_fixture(self, max_candidates: int = 4) -> dict:
        sheets_response = self.client.get("/raw-sheets")
        self.assertEqual(sheets_response.status_code, 200)
        sheet = sheets_response.json()["sheets"][0]
        response = self.client.post(
            "/view-candidates",
            json={
                "sheet_path": sheet["path"],
                "asset_id": "mario",
                "max_candidates": max_candidates,
                "ai_rank": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _write_candidate_run_fixture(self, name: str, records: list[dict]) -> str:
        from PIL import Image

        run_dir = WORKSPACE_ROOT / "outputs" / "studio_api" / "manual_smoke" / name
        shutil.rmtree(run_dir, ignore_errors=True)
        candidate_dir = run_dir / "candidates"
        candidate_dir.mkdir(parents=True)
        report_records = []
        for record in records:
            candidate_id = int(record["candidate_id"])
            color = tuple(record.get("color", (255, 0, 0, 255)))
            path = record.get("path")
            if path is None:
                path = candidate_dir / f"candidate_{candidate_id:03d}.png"
            else:
                path = Path(path)
                if not path.is_absolute():
                    path = run_dir / path
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (16, 16), color).save(path)
            report_records.append(
                {
                    "candidate_id": candidate_id,
                    "path": str(path),
                    "bbox": record.get("bbox", [candidate_id, candidate_id + 1, candidate_id + 2, candidate_id + 3]),
                    "size": [16, 16],
                    "has_alpha": True,
                    "deterministic_pose_hint": record.get("deterministic_pose_hint", "fixture"),
                }
            )
        Image.new("RGBA", (64, 16), (255, 255, 0, 255)).save(run_dir / "candidate_contact_sheet.png")
        (run_dir / "candidate_report.json").write_text(
            json.dumps(
                {
                    "schema": "spritespatial_view_candidates_v2",
                    "candidate_dir": str(candidate_dir),
                    "candidate_contact_sheet": str(run_dir / "candidate_contact_sheet.png"),
                    "candidates": report_records,
                }
            ),
            encoding="utf-8",
        )
        return str(run_dir.relative_to(WORKSPACE_ROOT)).replace("\\", "/")

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self._record("health", True, data)

    def test_assets_endpoint(self) -> None:
        response = self.client.get("/assets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = {item["asset_id"] for item in data["assets"]}
        self.assertIn("hero_side_fixture", ids)
        self._record("assets", True, {"asset_count": len(ids)})

    def test_presets_endpoint(self) -> None:
        response = self.client.get("/presets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        profiles = {item["profile_id"] for item in data["profiles"]}
        self.assertIn("fantasy_humanoid", profiles)
        profile_response = self.client.get("/presets/fantasy_humanoid")
        self.assertEqual(profile_response.status_code, 200)
        preset_ids = {item["preset_id"] for item in profile_response.json()["profile"]["presets"]}
        self.assertIn("pull_hat_back", preset_ids)
        self._record("presets", True, {"profiles": sorted(profiles)})

    def test_raw_sheets_file_serving_and_candidates(self) -> None:
        sheets_response = self.client.get("/raw-sheets")
        self.assertEqual(sheets_response.status_code, 200)
        sheets_data = sheets_response.json()
        sheets = sheets_data["sheets"]
        self.assertGreaterEqual(len(sheets), 1)
        mario_sheet = next(
            (sheet for sheet in sheets if sheet["filename"] == "SNES - Super Mario World - Playable Characters - Mario.png"),
            sheets[0],
        )
        self.assertTrue(mario_sheet["path"].startswith("assets/raw/"))
        self.assertGreater(mario_sheet["width"], 0)
        self.assertGreater(mario_sheet["height"], 0)

        file_response = self.client.get("/file", params={"path": mario_sheet["path"]})
        self.assertEqual(file_response.status_code, 200)
        self.assertTrue(file_response.headers["content-type"].startswith("image/"))

        traversal_response = self.client.get("/file", params={"path": "../secret.png"})
        self.assertEqual(traversal_response.status_code, 400)

        candidate_response = self.client.post(
            "/view-candidates",
            json={
                "sheet_path": mario_sheet["path"],
                "asset_id": "mario",
                "max_candidates": 12,
                "ai_rank": False,
            },
        )
        self.assertEqual(candidate_response.status_code, 200)
        candidate_data = candidate_response.json()
        self.assertTrue(candidate_data["ok"])
        self.assertEqual(len(candidate_data["candidates"]), 12)
        self.assertTrue((WORKSPACE_ROOT / candidate_data["candidate_contact_sheet"]).exists())
        self.assertTrue(candidate_data["candidate_contact_sheet"].startswith("outputs/"))
        self._record(
            "raw_sheets_file_serving_and_candidates",
            True,
            {
                "sheet": mario_sheet["path"],
                "candidate_count": len(candidate_data["candidates"]),
                "out_dir": candidate_data["out_dir"],
            },
        )

    def test_upload_raw_sheet(self) -> None:
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGBA", (24, 32), (255, 0, 255, 255)).save(buffer, format="PNG")
        response = self.client.post(
            "/raw-sheets/upload",
            params={"filename": "studio_upload_sheet_10b.png"},
            content=buffer.getvalue(),
            headers={"content-type": "image/png"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["sheet"]["filename"], "studio_upload_sheet_10b.png")
        self.assertEqual(data["sheet"]["width"], 24)
        self.assertEqual(data["sheet"]["height"], 32)

        sheets_response = self.client.get("/raw-sheets")
        self.assertEqual(sheets_response.status_code, 200)
        sheet_paths = {sheet["path"] for sheet in sheets_response.json()["sheets"]}
        self.assertIn(data["sheet"]["path"], sheet_paths)

        file_response = self.client.get("/file", params={"path": data["sheet"]["path"]})
        self.assertEqual(file_response.status_code, 200)

    def test_create_asset_from_candidate_fixture(self) -> None:
        asset_id = "studio_test_asset_9d"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        fixture = self._candidate_fixture(4)
        create_response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": asset_id,
                "candidate_run_dir": fixture["out_dir"],
                "selection_version": "view_selection_v1",
                "mode": "strict",
                "selection": {"front": 0, "side": 2, "back": 1},
                "source_coverage": {
                    "front": "authored",
                    "back": "authored",
                    "left": "authored_side",
                    "right": "authored_side",
                },
            },
        )
        self.assertEqual(create_response.status_code, 200)
        data = create_response.json()
        self.assertTrue(data["ok"])
        asset_dir = WORKSPACE_ROOT / data["asset_dir"]
        self.assertTrue((asset_dir / "spriteasset_v1.json").exists())
        self.assertTrue((asset_dir / "embodiment_params_default.json").exists())
        self.assertTrue((asset_dir / "embodiment_params.json").exists())
        for view in ("front", "side", "back"):
            self.assertTrue((asset_dir / f"{view}.png").exists())
        for label in ("outline", "head", "face", "hat_hair", "torso", "left_arm", "right_arm", "left_leg", "right_leg", "boots_feet", "equipment"):
            self.assertTrue((asset_dir / "semantic_overrides" / f"{label}.png").exists())
        spriteasset = json.loads((asset_dir / "spriteasset_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(spriteasset["schema_version"], "spriteasset_v1")
        self.assertTrue((asset_dir / "view_selection_v1.json").exists())
        self.assertEqual(spriteasset["view_selection"]["version"], "view_selection_v1")
        self.assertEqual(spriteasset["source_sprites"]["left"], "side.png")
        self.assertEqual(spriteasset["source_sprites"]["right"], "side.png")
        assets_response = self.client.get("/assets")
        self.assertEqual(assets_response.status_code, 200)
        self.assertIn(asset_id, {item["asset_id"] for item in assets_response.json()["assets"]})
        self._record("create_asset_from_candidate_fixture", True, {"asset_id": asset_id, "asset_dir": data["asset_dir"]})

    def test_rename_and_delete_asset(self) -> None:
        source_id = "studio_test_rename_source_10c"
        renamed_id = "studio_test_renamed_10c"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / source_id, ignore_errors=True)
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / renamed_id, ignore_errors=True)
        run_dir = self._write_candidate_run_fixture(
            "rename_delete_asset",
            [
                {"candidate_id": 0, "color": (255, 0, 0, 255), "deterministic_pose_hint": "front"},
                {"candidate_id": 1, "color": (0, 255, 0, 255), "deterministic_pose_hint": "back"},
                {"candidate_id": 2, "color": (0, 0, 255, 255), "deterministic_pose_hint": "side"},
            ],
        )
        create_response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": source_id,
                "candidate_run_dir": run_dir,
                "selection_version": "view_selection_v1",
                "mode": "strict",
                "selection": {"front": 0, "side": 2, "back": 1},
                "source_coverage": {"front": "authored", "back": "authored", "left": "authored_side", "right": "authored_side"},
            },
        )
        self.assertEqual(create_response.status_code, 200)

        rename_response = self.client.patch(f"/assets/{source_id}", json={"new_asset_id": renamed_id})
        self.assertEqual(rename_response.status_code, 200)
        self.assertFalse((WORKSPACE_ROOT / "assets" / "samples" / source_id).exists())
        renamed_dir = WORKSPACE_ROOT / "assets" / "samples" / renamed_id
        self.assertTrue((renamed_dir / "spriteasset_v1.json").exists())
        spriteasset = json.loads((renamed_dir / "spriteasset_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(spriteasset["asset_name"], renamed_id)
        view_selection = json.loads((renamed_dir / "view_selection_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(view_selection["asset_id"], renamed_id)

        duplicate_response = self.client.patch(f"/assets/{renamed_id}", json={"new_asset_id": "hero"})
        self.assertEqual(duplicate_response.status_code, 409)

        delete_response = self.client.delete(f"/assets/{renamed_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(renamed_dir.exists())

    def test_delete_asset_action_fallback(self) -> None:
        asset_id = "studio_test_delete_action_10c"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        run_dir = self._write_candidate_run_fixture(
            "delete_action_asset",
            [
                {"candidate_id": 0, "color": (255, 0, 0, 255), "deterministic_pose_hint": "front"},
                {"candidate_id": 1, "color": (0, 255, 0, 255), "deterministic_pose_hint": "back"},
                {"candidate_id": 2, "color": (0, 0, 255, 255), "deterministic_pose_hint": "side"},
            ],
        )
        create_response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": asset_id,
                "candidate_run_dir": run_dir,
                "selection_version": "view_selection_v1",
                "mode": "strict",
                "selection": {"front": 0, "side": 2, "back": 1},
                "source_coverage": {"front": "authored", "side": "authored", "back": "authored"},
            },
        )
        self.assertEqual(create_response.status_code, 200)
        asset_dir = WORKSPACE_ROOT / "assets" / "samples" / asset_id
        self.assertTrue(asset_dir.exists())

        delete_response = self.client.post(f"/assets/{asset_id}/delete")
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(asset_dir.exists())

    def test_create_asset_rejects_bad_inputs(self) -> None:
        fixture = self._candidate_fixture(2)
        unsafe_response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": "Bad Asset",
                "candidate_run_dir": fixture["out_dir"],
                "selection": {"front": 0, "side": 1, "back": 0},
                "source_coverage": {"front": "authored"},
            },
        )
        self.assertEqual(unsafe_response.status_code, 400)

        missing_front_response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": "studio_missing_front_9d",
                "candidate_run_dir": fixture["out_dir"],
                "selection": {"back": 1},
                "source_coverage": {"back": "authored"},
            },
        )
        self.assertEqual(missing_front_response.status_code, 400)

    def test_create_asset_rejects_duplicate_asset(self) -> None:
        asset_id = "studio_test_duplicate_9d"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        fixture = self._candidate_fixture(3)
        payload = {
            "asset_id": asset_id,
            "candidate_run_dir": fixture["out_dir"],
            "selection_version": "view_selection_v1",
            "mode": "strict",
            "selection": {"front": 0, "side": 1, "back": 2},
            "source_coverage": {"front": "authored"},
        }
        first_response = self.client.post("/assets/from-candidates", json=payload)
        self.assertEqual(first_response.status_code, 200)
        duplicate_response = self.client.post("/assets/from-candidates", json=payload)
        self.assertEqual(duplicate_response.status_code, 409)
        self._record("create_asset_rejects_duplicate_asset", True, {"asset_id": asset_id})

    def test_create_asset_resolves_candidate_id_and_copies_crop(self) -> None:
        from PIL import Image

        asset_id = "studio_test_candidate_contract_9f2"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        run_dir = self._write_candidate_run_fixture(
            "candidate_contract_9f2",
            [
                {"candidate_id": 10, "color": (255, 0, 0, 255)},
                {"candidate_id": 20, "color": (0, 0, 255, 255)},
                {"candidate_id": 30, "color": (0, 255, 0, 255)},
            ],
        )
        response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": asset_id,
                "candidate_run_dir": run_dir,
                "selection_version": "view_selection_v1",
                "mode": "strict",
                "selection": {"front": 20, "side": 30, "back": 10},
                "source_coverage": {"front": "authored"},
            },
        )
        self.assertEqual(response.status_code, 200)
        asset_dir = WORKSPACE_ROOT / "assets" / "samples" / asset_id
        with Image.open(asset_dir / "front.png") as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 255))
        spriteasset = json.loads((asset_dir / "spriteasset_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(spriteasset["source_sprites"]["front"], "front.png")
        self.assertNotIn("assets/raw", json.dumps(spriteasset))
        self.assertEqual(spriteasset["candidate_selection"]["front"]["candidate_id"], 20)
        self.assertEqual(spriteasset["view_selection"]["side"]["candidate_id"], 30)

    def test_strict_view_selection_rejects_missing_required_views(self) -> None:
        run_dir = self._write_candidate_run_fixture(
            "strict_required_views_10a",
            [
                {"candidate_id": 1, "color": (255, 0, 0, 255)},
                {"candidate_id": 2, "color": (0, 255, 0, 255)},
            ],
        )
        cases = [
            ({}, "Front view is required."),
            ({"front": 1}, "Side view is required in strict mode."),
            ({"front": 1, "side": 2}, "Back view is required in strict mode."),
        ]
        for selection, message in cases:
            response = self.client.post(
                "/assets/from-candidates",
                json={
                    "asset_id": f"studio_test_missing_{len(selection)}_10a",
                    "candidate_run_dir": run_dir,
                    "selection_version": "view_selection_v1",
                    "mode": "strict",
                    "selection": selection,
                    "source_coverage": {},
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn(message, response.text)

    def test_prototype_view_selection_allows_front_only_with_warnings(self) -> None:
        asset_id = "studio_test_prototype_10a"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        run_dir = self._write_candidate_run_fixture(
            "prototype_front_only_10a",
            [{"candidate_id": 1, "color": (255, 0, 0, 255)}],
        )
        response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": asset_id,
                "candidate_run_dir": run_dir,
                "selection_version": "view_selection_v1",
                "mode": "prototype",
                "selection": {"front": 1},
                "source_coverage": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Back will be inferred. Fidelity will be limited.", data["warnings"])
        asset_dir = WORKSPACE_ROOT / "assets" / "samples" / asset_id
        self.assertTrue((asset_dir / "side.png").exists())
        view_selection = json.loads((asset_dir / "view_selection_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(view_selection["views"]["side"]["authority"], "inferred_required_later")

    def test_create_asset_rejects_missing_candidate_id(self) -> None:
        run_dir = self._write_candidate_run_fixture(
            "candidate_missing_id_9f2",
            [{"candidate_id": 10, "color": (255, 0, 0, 255)}],
        )
        response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": "studio_test_missing_candidate_9f2",
                "candidate_run_dir": run_dir,
                "mode": "prototype",
                "selection": {"front": 11},
                "source_coverage": {"front": "authored"},
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_create_asset_rejects_candidate_path_outside_candidates_dir(self) -> None:
        run_dir = self._write_candidate_run_fixture(
            "candidate_unsafe_path_9f2",
            [{"candidate_id": 5, "path": "candidate_contact_sheet.png", "color": (255, 255, 0, 255)}],
        )
        response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": "studio_test_unsafe_candidate_9f2",
                "candidate_run_dir": run_dir,
                "mode": "prototype",
                "selection": {"front": 5},
                "source_coverage": {"front": "authored"},
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_candidate_across_views_creates_warning(self) -> None:
        asset_id = "studio_test_strict_success_10a"
        shutil.rmtree(WORKSPACE_ROOT / "assets" / "samples" / asset_id, ignore_errors=True)
        run_dir = self._write_candidate_run_fixture(
            "duplicate_warning_10a",
            [{"candidate_id": 1, "color": (255, 0, 0, 255)}],
        )
        response = self.client.post(
            "/assets/from-candidates",
            json={
                "asset_id": asset_id,
                "candidate_run_dir": run_dir,
                "selection_version": "view_selection_v1",
                "mode": "strict",
                "selection": {"front": 1, "side": 1, "back": 1},
                "source_coverage": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Same candidate used for multiple views.", response.json()["warnings"])

    def test_build_asset_rejects_full_sheet_sized_front_sprite(self) -> None:
        from PIL import Image

        asset_id = "studio_test_full_sheet_guard_9f2"
        asset_dir = WORKSPACE_ROOT / "assets" / "samples" / asset_id
        shutil.rmtree(asset_dir, ignore_errors=True)
        asset_dir.mkdir(parents=True)
        Image.new("RGBA", (300, 300), (255, 0, 0, 255)).save(asset_dir / "front.png")
        (asset_dir / "spriteasset_v1.json").write_text(
            json.dumps(
                {
                    "schema_version": "spriteasset_v1",
                    "asset_name": asset_id,
                    "asset_type": "character",
                    "source_sprites": {"front": "front.png"},
                }
            ),
            encoding="utf-8",
        )
        response = self.client.post("/jobs/build-asset", json={"asset_id": asset_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Front sprite appears to be a full sheet", response.text)

    def test_build_job_lifecycle_with_mocked_builder(self) -> None:
        def fake_run(command: list[str], cwd: Path, text: bool, capture_output: bool) -> subprocess.CompletedProcess:
            out_dir = Path(cwd) / command[command.index("--out") + 1]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "validation_report.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "mesh_connected_components": 1,
                        "degenerate_face_count": 0,
                        "non_manifold_after_cleanup": 0,
                        "semantic_label_preservation_passed": True,
                    }
                ),
                encoding="utf-8",
            )
            mesh = {
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "indices": [0, 1, 2],
            }
            for name in ("topological_model.json", "mesh.json", "mesh_topology_cleaned.json"):
                (out_dir / name).write_text(json.dumps(mesh) + "\n", encoding="utf-8")
            (out_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with patch("studio_api.services.subprocess.run", side_effect=fake_run):
            response = self.client.post("/jobs/build-asset", json={"asset_id": "hero_side_fixture"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])
            job_id = data["job_id"]
            detail = self._wait_for_job(job_id)

        self.assertEqual(detail["status"], "completed")
        self.assertTrue(detail["validation_report"]["passed"])
        self.assertIn("validation_report", detail["artifacts"])
        self.assertIn("mesh", detail["artifacts"])
        list_response = self.client.get("/jobs")
        self.assertEqual(list_response.status_code, 200)
        listed_jobs = list_response.json()["jobs"]
        self.assertIn(job_id, {item["job_id"] for item in listed_jobs})
        listed_job = next(item for item in listed_jobs if item["job_id"] == job_id)
        self.assertIn("mesh", listed_job["artifacts"])
        self.assertTrue(listed_job["validation_report"]["passed"])
        self._record("build_job_lifecycle_with_mocked_builder", True, {"job_id": job_id})

    def test_build_job_rejects_invalid_asset(self) -> None:
        response = self.client.post("/jobs/build-asset", json={"asset_id": "missing_asset_for_9e"})
        self.assertEqual(response.status_code, 404)

    def test_build_job_failed_state_with_mocked_builder(self) -> None:
        def fake_fail(command: list[str], cwd: Path, text: bool, capture_output: bool) -> subprocess.CompletedProcess:
            out_dir = Path(cwd) / command[command.index("--out") + 1]
            out_dir.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="mock builder failed")

        with patch("studio_api.services.subprocess.run", side_effect=fake_fail):
            response = self.client.post("/jobs/build-asset", json={"asset_id": "hero_side_fixture"})
            self.assertEqual(response.status_code, 200)
            job_id = response.json()["job_id"]
            detail = self._wait_for_job(job_id)

        self.assertEqual(detail["status"], "failed")
        self.assertIn("mock builder failed", detail["error"])
        self._record("build_job_failed_state_with_mocked_builder", True, {"job_id": job_id})

    def test_apply_preset_and_fast_diff(self) -> None:
        apply_response = self.client.post(
            "/apply-preset",
            json={
                "asset_id": "hero_side_fixture",
                "base_params": "assets/samples/hero_side_fixture/embodiment_params_default.json",
                "preset_profile": "fantasy_humanoid",
                "preset_id": "pull_hat_back",
                "intensity": 0.75,
                "run_diff": False,
                "fast_smoke": True,
            },
        )
        self.assertEqual(apply_response.status_code, 200)
        apply_data = apply_response.json()
        self.assertTrue(apply_data["ok"])
        self.assertTrue(apply_data["run_id"])
        edited_params = apply_data["edited_params_path"]
        self.assertTrue((WORKSPACE_ROOT / edited_params).exists())
        report = apply_data["preset_application_report"]
        self.assertEqual(report["applied_parts"], ["hair/hat"])

        diff_response = self.client.post(
            "/run-diff",
            json={
                "asset_id": "hero_side_fixture",
                "base_params": "assets/samples/hero_side_fixture/embodiment_params_default.json",
                "edited_params": edited_params,
                "label_base": "default",
                "label_edited": "pull_hat_back",
                "fast_smoke": True,
            },
        )
        self.assertEqual(diff_response.status_code, 200)
        diff_data = diff_response.json()
        self.assertTrue(diff_data["ok"])
        self.assertTrue(diff_data["run_id"])
        self.assertTrue(diff_data["param_diff_report"]["edit_valid"])
        runs_response = self.client.get("/runs")
        self.assertEqual(runs_response.status_code, 200)
        run_ids = {item["run_id"] for item in runs_response.json()["runs"]}
        self.assertIn(apply_data["run_id"], run_ids)
        run_response = self.client.get(f"/runs/{apply_data['run_id']}")
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["run"]["run_id"], apply_data["run_id"])
        self._record(
            "apply_preset_and_fast_diff",
            True,
            {
                "edited_params": edited_params,
                "diff_out": diff_data["out_dir"],
            },
        )

    def _wait_for_job(self, job_id: str, timeout_seconds: float = 5.0) -> dict:
        deadline = time.time() + timeout_seconds
        last_detail = {}
        while time.time() < deadline:
            detail_response = self.client.get(f"/jobs/{job_id}")
            self.assertEqual(detail_response.status_code, 200)
            last_detail = detail_response.json()["job"]
            if last_detail["status"] in {"completed", "failed"}:
                return last_detail
            time.sleep(0.05)
        self.fail(f"Job did not finish in test timeout: {last_detail}")


if __name__ == "__main__":
    unittest.main()
