from __future__ import annotations

import json
import unittest
from pathlib import Path


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


@unittest.skipIf(TestClient is None, f"FastAPI test dependencies unavailable: {IMPORT_ERROR}")
class StudioApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        SMOKE_DIR.mkdir(parents=True, exist_ok=True)
        cls.report: dict[str, object] = {"schema": "spritespatial_studio_api_smoke_report_v1", "checks": []}

    @classmethod
    def tearDownClass(cls) -> None:
        (SMOKE_DIR / "api_smoke_report.json").write_text(json.dumps(cls.report, indent=2) + "\n", encoding="utf-8")

    def _record(self, name: str, ok: bool, payload: object | None = None) -> None:
        self.report["checks"].append({"name": name, "ok": ok, "payload": payload})

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


if __name__ == "__main__":
    unittest.main()
