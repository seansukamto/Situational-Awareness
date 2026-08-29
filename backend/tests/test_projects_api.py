import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.projects.repository import SQLiteRepository
from app.projects.models import ProjectCreate
from app.simulation import build_demo_store


def test_demo_bootstrap_and_analysis(tmp_path):
    app.state.repository = SQLiteRepository(tmp_path / "demo.sqlite3")
    with TestClient(app) as client:
        first = client.post("/api/demo/bootstrap")
        second = client.post("/api/demo/bootstrap")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["project"]["id"] == "project_demo_sg_01"
        assert len(second.json()["bills"]) == 1
        staff = client.get("/api/projects/project_demo_sg_01/staff").json()
        templates = client.get("/api/projects/project_demo_sg_01/task-templates").json()
        days = client.get("/api/projects/project_demo_sg_01/game-days").json()
        assert [profile["display_name"] for profile in staff] == [
            "Aisha Rahman",
            "Daniel Tan",
            "Lucas Wong",
            "Maya Lim",
        ]
        assert len(templates) == 6
        assert {template["domain"] for template in templates} == {
            "energy", "water", "waste", "food", "transport", "buying"
        }
        assert days[0]["id"] == "day_demo_showcase"
        assert days[0]["status"] == "completed"
        leaderboard = client.get(
            "/api/projects/project_demo_sg_01/game-days/day_demo_showcase/leaderboard"
        ).json()
        assert len(leaderboard) == 4
        assert sum(item["tasks_completed"] for item in leaderboard) == 5
        events = client.get(
            "/api/projects/project_demo_sg_01/game-days/day_demo_showcase/events"
        ).json()
        assert events[-1]["type"] == "day_completed"
        assert events[0]["occurred_at"] != events[-1]["occurred_at"]

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
        assert "profit_margin_impact" in body["metrics"]
        assert "customer_service_incidents" in body["metrics"]
        report = client.get(
            f"/api/projects/project_demo_sg_01/analyses/{body['id']}/report.md"
        )
        assert report.status_code == 200
        assert "Proceed to a time-boxed in-store pilot" in report.text
        assert "raw utility file was not retained" in report.text


def test_demo_bootstrap_refreshes_an_older_store_model(tmp_path):
    repository = SQLiteRepository(tmp_path / "upgrade.sqlite3")
    old_store = build_demo_store()
    old_store.customers = []
    repository.create_project(
        ProjectCreate(name="Old demo", store=old_store),
        project_id="project_demo_sg_01",
    )
    app.state.repository = repository
    with TestClient(app) as client:
        response = client.post("/api/demo/bootstrap")
        assert response.status_code == 200
        assert len(response.json()["project"]["store"]["customers"]) == 4


def test_demo_bootstrap_is_safe_when_multiple_tabs_load_together(tmp_path):
    app.state.repository = SQLiteRepository(tmp_path / "concurrent-demo.sqlite3")
    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=3) as executor:
            responses = list(executor.map(
                lambda _: client.post("/api/demo/bootstrap"),
                range(3),
            ))

        assert [response.status_code for response in responses] == [200, 200, 200]
        staff = client.get("/api/projects/project_demo_sg_01/staff").json()
        templates = client.get("/api/projects/project_demo_sg_01/task-templates").json()
        assert len(staff) == 4
        assert len(templates) == 6


def test_store_settings_persist_and_drive_simulation(tmp_path):
    app.state.repository = SQLiteRepository(tmp_path / "store-settings.sqlite3")
    with TestClient(app) as client:
        project = client.post("/api/demo/bootstrap").json()["project"]
        store = project["store"]
        payload = {
            "name": "Orchard Night Store",
            "timezone": "Asia/Singapore",
            "floor_area_m2": 735,
            "opening_minute": 600,
            "closing_minute": 1350,
            "tariff_sgd_per_kwh": 0.41,
            "grid_emission_factor_kg_per_kwh": 0.39,
        }
        updated = client.put(
            "/api/projects/project_demo_sg_01/store",
            json=payload,
        )
        assert updated.status_code == 200
        assert updated.json()["store"]["name"] == "Orchard Night Store"
        assert updated.json()["store"]["floor_area_m2"] == 735
        assert updated.json()["store"]["zones"] == store["zones"]

        comparison = client.get(
            "/api/simulations/compare",
            params={"seed": 42, "project_id": "project_demo_sg_01"},
        )
        assert comparison.status_code == 200
        assert comparison.json()["baseline_run"]["store"]["name"] == "Orchard Night Store"
        assert comparison.json()["baseline_run"]["store"]["closing_minute"] == 1350


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
        assert bill["filename"] == "uploaded_utility_bill.json"

        confirmed = client.post(
            f"/api/projects/project_demo_sg_01/bills/{bill['id']}/confirm",
            json=payload,
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["average_tariff_sgd_per_kwh"] == 0.32


def test_staff_checklist_is_scoped_and_completable(tmp_path):
    repository = SQLiteRepository(tmp_path / "checklist.sqlite3")
    app.state.repository = repository
    with TestClient(app) as client:
        client.post("/api/demo/bootstrap")
        project = repository.get_project("project_demo_sg_01")
        assert project is not None
        project.store.agents[0].assigned_equipment_ids.append("cold_storage")
        repository.update_store(project.id, project.store)
        response = client.post("/api/projects/project_demo_sg_01/checklists")
        assert response.status_code == 201
        checklist = response.json()
        assert checklist["tasks"]
        assert all(task["equipment_id"] != "cold_storage" for task in checklist["tasks"])
        assert {task["equipment_id"] for task in checklist["tasks"]} == {
            "checkout_pos",
            "demo_displays",
            "display_wall_lights",
            "stockroom_lights",
        }

        token = checklist["token"]
        missing = client.post(f"/api/checklists/{token}/tasks/missing/complete")
        assert missing.status_code == 404
        for task in checklist["tasks"]:
            completed = client.post(
                f"/api/checklists/{token}/tasks/{task['id']}/complete"
            )
            assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        saved = repository.get_checklist(token)
        assert saved is not None
        repository.update_checklist(
            saved.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
        )
        assert client.get(f"/api/checklists/{token}").status_code == 410

        privacy = client.get("/api/privacy")
        assert privacy.status_code == 200
        assert privacy.json()["raw_utility_files_retained"] is False
