import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.projects.models import ProjectCreate
from app.projects.repository import SQLiteRepository
from app.simulation import build_demo_store


def test_run_schema_is_idempotent_and_demo_is_not_backfilled(tmp_path):
    database = tmp_path / "runs.sqlite3"
    SQLiteRepository(database)
    repository = SQLiteRepository(database)
    app.state.repository = repository

    with TestClient(app) as client:
        assert client.post("/api/demo/bootstrap").status_code == 200
        history = client.get("/api/projects/project_demo_sg_01/runs")
        assert history.status_code == 200
        assert history.json() == []

    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM simulation_runs").fetchone()[0]
    assert count == 0


def test_one_paired_run_persists_and_is_project_scoped(tmp_path):
    database = tmp_path / "paired.sqlite3"
    repository = SQLiteRepository(database)
    app.state.repository = repository

    with TestClient(app) as client:
        bootstrap = client.post("/api/demo/bootstrap").json()
        created = client.post(
            "/api/projects/project_demo_sg_01/runs",
            json={"seed": 91, "sample_count": 25},
        )
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "completed"
        assert run["seed"] == 91
        assert run["sample_count"] == 25
        assert run["comparison"]["baseline_run"]["scenario_id"] == "baseline"
        assert run["comparison"]["intervention_run"]["scenario_id"] == "green-close"
        assert run["comparison"]["baseline_run"]["events"]
        assert run["comparison"]["intervention_run"]["events"]
        assert run["impact_analysis"]["sample_count"] == 25
        assert run["store_snapshot"] == bootstrap["project"]["store"]
        assert run["scenario_settings_snapshot"] == bootstrap["project"]["settings"]
        assert run["evidence_snapshot"]["status"] == "confirmed"
        assert run["baseline_explanations"]
        assert run["intervention_explanations"]
        assert run["game_master_rules_version"]
        assert run["agent_mode"] == "deterministic"
        assert run["agent_provider"] == "deterministic"
        assert run["agent_model"] == "situational-awareness-rules"
        assert run["prompt_template_version"]
        assert run["provider_configuration_fingerprint"]
        assert run["agent_settings_snapshot"]["mode"] == "deterministic"
        assert run["agent_usage"]["provider_calls"] == 0
        assert run["comparison"]["intervention_run"]["agent_decisions"]
        assert any(
            event["type"] == "agent_proposal"
            for event in run["comparison"]["intervention_run"]["events"]
        )
        assert {rule["id"] for rule in run["game_master_rules_snapshot"]} == {
            "protected_loads",
            "role_authorization",
            "customer_presence",
            "immutable_snapshot",
        }

        history = client.get("/api/projects/project_demo_sg_01/runs").json()
        assert len(history) == 1
        assert history[0]["id"] == run["id"]
        assert history[0]["configuration_current"] is True
        assert history[0]["estimated_savings_sgd"] is not None
        assert history[0]["agent_mode"] == "deterministic"
        assert history[0]["provider_calls"] == 0

        other = repository.create_project(
            ProjectCreate(name="Other project", store=build_demo_store())
        )
        assert client.get(f"/api/projects/{other.id}/runs").json() == []
        assert client.get(f"/api/projects/{other.id}/runs/{run['id']}").status_code == 404

    reloaded = SQLiteRepository(database)
    persisted = reloaded.get_simulation_run("project_demo_sg_01", run["id"])
    assert persisted is not None
    assert persisted.comparison is not None
    assert persisted.comparison.baseline_run.seed == 91

    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM simulation_runs").fetchone()[0]
    assert count == 1


def test_unconfigured_generative_mode_completes_with_labelled_fallback(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    repository = SQLiteRepository(tmp_path / "provider-fallback.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        client.post("/api/demo/bootstrap")
        response = client.post(
            "/api/projects/project_demo_sg_01/runs",
            json={
                "mode": "openai",
                "seed": 2026,
                "sample_count": 25,
                "max_calls": 2,
                "max_calls_per_agent": 2,
            },
        )

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "completed"
    assert run["agent_mode"] == "openai"
    assert run["agent_usage"]["fallback_decisions"] > 0
    events = (
        run["comparison"]["baseline_run"]["events"]
        + run["comparison"]["intervention_run"]["events"]
    )
    assert any(event["type"] == "provider_failure" for event in events)
    assert any(event["type"] == "provider_fallback" for event in events)
    proposals = [event for event in events if event["type"] == "agent_proposal"]
    assert proposals
    assert all(event["data"]["generated_by_ai"] is False for event in proposals)


def test_configuration_change_marks_history_outdated_without_mutating_snapshot(tmp_path):
    repository = SQLiteRepository(tmp_path / "outdated.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project = client.post("/api/demo/bootstrap").json()["project"]
        first = client.post(
            "/api/projects/project_demo_sg_01/runs",
            json={"seed": 42, "sample_count": 25},
        ).json()
        old_name = first["store_snapshot"]["name"]

        store = project["store"]
        updated_settings = {
            "name": "Configured Orchard Store",
            "timezone": store["timezone"],
            "floor_area_m2": 725,
            "opening_minute": store["opening_minute"],
            "closing_minute": store["closing_minute"],
            "tariff_sgd_per_kwh": store["tariff_sgd_per_kwh"],
            "grid_emission_factor_kg_per_kwh": store[
                "grid_emission_factor_kg_per_kwh"
            ],
        }
        assert client.put(
            "/api/projects/project_demo_sg_01/store",
            json=updated_settings,
        ).status_code == 200

        history = client.get("/api/projects/project_demo_sg_01/runs").json()
        assert history[0]["configuration_current"] is False
        historical = client.get(
            f"/api/projects/project_demo_sg_01/runs/{first['id']}"
        ).json()
        assert historical["store_snapshot"]["name"] == old_name
        assert historical["store_snapshot"]["floor_area_m2"] == 180

        second = client.post(
            "/api/projects/project_demo_sg_01/runs",
            json={"seed": 173, "sample_count": 25},
        ).json()
        assert second["store_snapshot"]["name"] == "Configured Orchard Store"
        assert second["store_snapshot"]["floor_area_m2"] == 725

        history = client.get("/api/projects/project_demo_sg_01/runs").json()
        assert [item["id"] for item in history] == [second["id"], first["id"]]
        assert history[0]["configuration_current"] is True
        assert history[1]["configuration_current"] is False
