import json

from fastapi.testclient import TestClient

from app.main import app
from app.projects.repository import SQLiteRepository


def test_demo_bootstrap_and_analysis(tmp_path):
    app.state.repository = SQLiteRepository(tmp_path / "demo.sqlite3")
    with TestClient(app) as client:
        first = client.post("/api/demo/bootstrap")
        second = client.post("/api/demo/bootstrap")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["project"]["id"] == "project_demo_sg_01"
        assert len(second.json()["bills"]) == 1

        response = client.post(
            "/api/projects/project_demo_sg_01/analysis",
            json={"samples": 25, "seed": 17},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sample_count"] == 25
        assert body["metrics"]["annual_utility_savings"]["p90"] >= body["metrics"][
            "annual_utility_savings"
        ]["p10"]
        assert body["calibration"]["model_coverage_ratio"] < 1


def test_uploaded_bill_requires_confirmation(tmp_path):
    app.state.repository = SQLiteRepository(tmp_path / "upload.sqlite3")
    with TestClient(app) as client:
        client.post("/api/demo/bootstrap")
        payload = {
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "total_kwh": 4500,
            "total_cost_sgd": 1440,
        }
        response = client.post(
            "/api/projects/project_demo_sg_01/bills/upload",
            files={
                "bill_file": (
                    "june.json",
                    json.dumps(payload).encode(),
                    "application/json",
                )
            },
        )
        assert response.status_code == 201
        bill = response.json()
        assert bill["status"] == "needs_confirmation"
        assert bill["raw_file_retained"] is False

        confirmed = client.post(
            f"/api/projects/project_demo_sg_01/bills/{bill['id']}/confirm",
            json=payload,
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["average_tariff_sgd_per_kwh"] == 0.32
