import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.projects.models import ProjectCreate
from app.projects.repository import SQLiteRepository
from app.simulation import build_demo_store


def staff_payload(**overrides):
    payload = {
        "display_name": "Alex Tan",
        "role": "closing_associate",
        "avatar_id": "associate",
        "authorized_zone_ids": ["sales_floor"],
        "authorized_equipment_ids": ["demo_displays"],
        "default_shift_start": 9 * 60,
        "default_shift_end": 22 * 60,
        "join_pin": "2468",
    }
    payload.update(overrides)
    return payload


def test_staff_schema_migration_is_idempotent(tmp_path):
    database = tmp_path / "staff.sqlite3"
    SQLiteRepository(database)
    SQLiteRepository(database)

    with sqlite3.connect(database) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_versions ORDER BY version"
        ).fetchall()
        staff_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'staff_profiles'"
        ).fetchone()

    assert versions == [(1,), (2,), (3,), (4,)]
    assert staff_table == ("staff_profiles",)


def test_staff_profiles_are_project_scoped_and_pins_are_not_exposed(tmp_path):
    repository = SQLiteRepository(tmp_path / "staff-api.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project = client.post("/api/demo/bootstrap").json()["project"]
        repository.reset_demo_game_content(project["id"])
        avatars = client.get("/api/avatars")
        assert avatars.status_code == 200
        assert {item["id"] for item in avatars.json()} >= {
            "associate",
            "shift-manager",
        }

        response = client.post(
            f"/api/projects/{project['id']}/staff",
            json=staff_payload(),
        )
        assert response.status_code == 201
        staff = response.json()
        assert staff["display_name"] == "Alex Tan"
        assert staff["normalized_name"] == "alex tan"
        assert "join_pin" not in staff
        assert "pin_hash" not in staff
        assert repository.verify_staff_pin(project["id"], staff["id"], "2468")
        assert not repository.verify_staff_pin(project["id"], staff["id"], "0000")

        listed = client.get(f"/api/projects/{project['id']}/staff")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [staff["id"]]

        other = repository.create_project(
            ProjectCreate(name="Other store", store=build_demo_store())
        )
        assert client.get(f"/api/projects/{other.id}/staff").json() == []
        assert client.put(
            f"/api/projects/{other.id}/staff/{staff['id']}",
            json={"display_name": "Wrong project"},
        ).status_code == 404


def test_staff_profile_validation_update_and_pin_reset(tmp_path):
    repository = SQLiteRepository(tmp_path / "staff-validation.sqlite3")
    app.state.repository = repository

    with TestClient(app) as client:
        project_id = client.post("/api/demo/bootstrap").json()["project"]["id"]
        repository.reset_demo_game_content(project_id)
        created = client.post(
            f"/api/projects/{project_id}/staff",
            json=staff_payload(),
        ).json()

        duplicate = client.post(
            f"/api/projects/{project_id}/staff",
            json=staff_payload(display_name="  ALEX   TAN  ", join_pin="1357"),
        )
        assert duplicate.status_code == 409

        assert client.post(
            f"/api/projects/{project_id}/staff",
            json=staff_payload(display_name="Avatar Error", avatar_id="remote-url"),
        ).status_code == 422
        assert client.post(
            f"/api/projects/{project_id}/staff",
            json=staff_payload(
                display_name="Zone Error",
                authorized_zone_ids=["unknown_zone"],
            ),
        ).status_code == 422
        assert client.post(
            f"/api/projects/{project_id}/staff",
            json=staff_payload(
                display_name="Equipment Error",
                authorized_equipment_ids=["unknown_equipment"],
            ),
        ).status_code == 422

        updated = client.put(
            f"/api/projects/{project_id}/staff/{created['id']}",
            json={
                "display_name": "Alexandra Tan",
                "avatar_id": "late-browser",
                "active": False,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["normalized_name"] == "alexandra tan"
        assert updated.json()["avatar_id"] == "late-browser"
        assert updated.json()["active"] is False

        reset = client.post(
            f"/api/projects/{project_id}/staff/{created['id']}/reset-pin",
            json={"join_pin": "9753"},
        )
        assert reset.status_code == 200
        assert not repository.verify_staff_pin(project_id, created["id"], "2468")

        reactivated = client.put(
            f"/api/projects/{project_id}/staff/{created['id']}",
            json={"active": True},
        )
        assert reactivated.status_code == 200
        assert repository.verify_staff_pin(project_id, created["id"], "9753")
