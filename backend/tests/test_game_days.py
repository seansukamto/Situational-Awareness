from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.projects.repository import SQLiteRepository


def create_staff(client: TestClient, project_id: str, name: str, pin: str = "2468") -> dict:
    response = client.post(
        f"/api/projects/{project_id}/staff",
        json={
            "display_name": name,
            "role": "closing_associate",
            "avatar_id": "associate",
            "authorized_zone_ids": ["stockroom"],
            "authorized_equipment_ids": ["stockroom_lights"],
            "default_shift_start": 480,
            "default_shift_end": 1440,
            "join_pin": pin,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_template(client: TestClient, project_id: str, **overrides) -> dict:
    payload = {
        "label": "Stockroom lights challenge",
        "description": "Switch off the stockroom lights when the task is released.",
        "domain": "energy",
        "zone_id": "stockroom",
        "equipment_id": "stockroom_lights",
        "allowed_roles": ["closing_associate"],
        "available_from_minute": 0,
        "available_until_minute": 1440,
        "expected_minutes": 5,
        "base_points": 50,
        "maximum_points": 100,
        "verification_method": "self_confirmation",
        "estimated_impact_value": 0.3,
        "estimated_impact_unit": "kWh",
    }
    payload.update(overrides)
    response = client.post(
        f"/api/projects/{project_id}/task-templates",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def create_started_day(client: TestClient, project_id: str) -> dict:
    created = client.post(
        f"/api/projects/{project_id}/game-days",
        json={"start_minute": 0, "end_minute": 1440},
    )
    assert created.status_code == 201
    started = client.post(
        f"/api/projects/{project_id}/game-days/{created.json()['id']}/start"
    )
    assert started.status_code == 200
    assert started.json()["status"] == "active"
    return started.json()


def join_headers(
    client: TestClient,
    day: dict,
    staff: dict,
    pin: str = "2468",
) -> dict[str, str]:
    joined = client.post(
        f"/api/game/join/{day['join_token']}",
        json={"staff_id": staff["id"], "join_pin": pin},
    )
    assert joined.status_code == 200
    return {"Authorization": f"Bearer {joined.json()['session_token']}"}


def test_game_day_task_marketplace_scoring_and_event_ledger(tmp_path):
    repository = SQLiteRepository(tmp_path / "game-day.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project_id = client.post("/api/demo/bootstrap").json()["project"]["id"]
        staff = create_staff(client, project_id, "Alex Tan")
        create_template(client, project_id)
        day = create_started_day(client, project_id)

        join_page = client.get(f"/api/game/join/{day['join_token']}")
        assert join_page.status_code == 200
        assert join_page.json()["staff"][0]["display_name"] == "Alex Tan"
        assert client.post(
            f"/api/game/join/{day['join_token']}",
            json={"staff_id": staff["id"], "join_pin": "0000"},
        ).status_code == 401
        headers = join_headers(client, day, staff)

        tasks = client.get("/api/game/tasks", headers=headers)
        assert tasks.status_code == 200
        assert len(tasks.json()) == 1
        task = tasks.json()[0]
        assert task["status"] == "available"

        claimed = client.post(
            f"/api/game/tasks/{task['id']}/claim",
            headers=headers,
        )
        assert claimed.status_code == 200
        assert claimed.json()["claimed_by_staff_id"] == staff["id"]

        released = client.post(
            f"/api/game/tasks/{task['id']}/release",
            headers=headers,
        )
        assert released.status_code == 200
        assert released.json()["status"] == "available"
        assert released.json()["claimed_by_staff_id"] is None

        reclaimed = client.post(
            f"/api/game/tasks/{task['id']}/claim",
            headers=headers,
        )
        assert reclaimed.status_code == 200

        completed = client.post(
            f"/api/game/tasks/{task['id']}/complete",
            headers=headers,
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["points_awarded"] == 55
        assert client.post(
            f"/api/game/tasks/{task['id']}/complete",
            headers=headers,
        ).status_code == 409

        leaderboard = client.get("/api/game/leaderboard", headers=headers)
        assert leaderboard.status_code == 200
        assert leaderboard.json() == [
            {
                "rank": 1,
                "staff_id": staff["id"],
                "display_name": "Alex Tan",
                "avatar_id": "associate",
                "points": 55,
                "tasks_completed": 1,
            }
        ]

        events = client.get(
            f"/api/projects/{project_id}/game-days/{day['id']}/events"
        ).json()
        assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
        assert {event["type"] for event in events} >= {
            "day_created",
            "day_started",
            "staff_joined",
            "task_released",
            "task_claimed",
            "task_released_by_staff",
            "task_completed",
            "points_awarded",
        }
        assert client.post(
            f"/api/projects/{project_id}/game-days/{day['id']}/close"
        ).json()["status"] == "completed"


def test_end_of_day_analysis_versions_and_applies_a_bounded_policy(tmp_path):
    repository = SQLiteRepository(tmp_path / "game-learning.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project_id = client.post("/api/demo/bootstrap").json()["project"]["id"]
        create_staff(client, project_id, "Ava Lim")
        create_template(client, project_id)
        day = create_started_day(client, project_id)

        closed = client.post(
            f"/api/projects/{project_id}/game-days/{day['id']}/close"
        )
        assert closed.status_code == 200
        analysis = client.get(
            f"/api/projects/{project_id}/game-days/{day['id']}/analysis"
        )
        assert analysis.status_code == 200
        assert analysis.json()["analyzer_mode"] == "deterministic"
        assert analysis.json()["metrics"]["tasks_released"] == 1
        assert analysis.json()["metrics"]["tasks_completed"] == 0
        assert analysis.json()["metrics"]["domain_performance"]["energy"]["completion_rate"] == 0

        policies = client.get(f"/api/projects/{project_id}/game-policies").json()
        assert len(policies) == 1
        assert policies[0]["active"] is True
        assert policies[0]["domain_point_multipliers"]["energy"] == 1.05
        assert all(0.9 <= value <= 1.1 for value in policies[0]["domain_point_multipliers"].values())

        tomorrow = date.fromisoformat(day["local_date"]) + timedelta(days=1)
        next_day = client.post(
            f"/api/projects/{project_id}/game-days",
            json={"local_date": tomorrow.isoformat(), "start_minute": 0, "end_minute": 1440},
        ).json()
        assert next_day["policy_version"] == policies[0]["version"]
        assert client.post(
            f"/api/projects/{project_id}/game-days/{next_day['id']}/start"
        ).status_code == 200
        next_tasks = repository.list_task_instances(next_day["id"])
        assert next_tasks[0].base_points == 52
        assert next_tasks[0].maximum_points == 105

        client.post(f"/api/projects/{project_id}/game-days/{day['id']}/close")
        assert len(client.get(f"/api/projects/{project_id}/game-policies").json()) == 1


def test_task_claim_is_atomic_and_only_one_staff_wins(tmp_path):
    repository = SQLiteRepository(tmp_path / "atomic-claim.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project_id = client.post("/api/demo/bootstrap").json()["project"]["id"]
        first = create_staff(client, project_id, "Alex Tan")
        second = create_staff(client, project_id, "Jamie Lim", "1357")
        create_template(client, project_id)
        day = create_started_day(client, project_id)
        task = repository.list_task_instances(day["id"])[0]

    now = datetime.now(UTC)

    def claim(staff_id: str):
        try:
            return repository.claim_task_instance(
                day["id"],
                task.id,
                staff_id,
                claimed_at=now,
                reservation_expires_at=now + timedelta(minutes=15),
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, [first["id"], second["id"]]))

    winners = [item for item in outcomes if not isinstance(item, str)]
    failures = [item for item in outcomes if isinstance(item, str)]
    assert len(winners) == 1
    assert failures == ["Task is no longer available"]
    stored = repository.get_task_instance(day["id"], task.id)
    assert stored is not None
    assert stored.claimed_by_staff_id in {first["id"], second["id"]}


def test_game_task_policy_rejects_protected_and_unauthorized_equipment(tmp_path):
    repository = SQLiteRepository(tmp_path / "task-policy.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project_id = client.post("/api/demo/bootstrap").json()["project"]["id"]
        protected = client.post(
            f"/api/projects/{project_id}/task-templates",
            json={
                "label": "Unsafe cold storage task",
                "description": "This must never enter the game marketplace.",
                "domain": "energy",
                "zone_id": "stockroom",
                "equipment_id": "cold_storage",
                "allowed_roles": ["manager"],
            },
        )
        assert protected.status_code == 422
        assert "Protected" in protected.json()["detail"]

        unauthorized = client.post(
            f"/api/projects/{project_id}/task-templates",
            json={
                "label": "Unauthorized checkout task",
                "description": "Associates cannot operate the manager-only POS.",
                "domain": "energy",
                "zone_id": "checkout",
                "equipment_id": "checkout_pos",
                "allowed_roles": ["closing_associate"],
            },
        )
        assert unauthorized.status_code == 422
        assert "authorized" in unauthorized.json()["detail"]
