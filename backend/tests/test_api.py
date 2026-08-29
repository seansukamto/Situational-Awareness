from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_comparison_endpoint():
    response = client.get("/api/simulations/compare", params={"seed": 42})
    assert response.status_code == 200
    body = response.json()
    assert body["baseline_run"]["scenario_id"] == "baseline"
    assert body["intervention_run"]["scenario_id"] == "green-close"
    assert body["energy_kwh"]["intervention"] <= body["energy_kwh"]["baseline"]


def test_event_explanations_are_grounded_in_sequence():
    response = client.get(
        "/api/simulations/explanations",
        params={"scenario_id": "green-close", "seed": 42},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["event_seq"] for item in body] == list(range(1, len(body) + 1))
    equipment = next(item for item in body if "protected equipment remains active" in item["rules_checked"])
    assert any(value.startswith("target ") for value in equipment["grounded_in"])
