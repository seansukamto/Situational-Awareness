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
