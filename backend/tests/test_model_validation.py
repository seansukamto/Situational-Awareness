import pytest
from pydantic import ValidationError

from app.simulation import build_demo_store, get_scenario


def test_store_rejects_unknown_equipment_assignment():
    payload = build_demo_store().model_dump()
    payload["agents"][0]["assigned_equipment_ids"] = ["missing_equipment"]
    with pytest.raises(ValidationError, match="known equipment"):
        type(build_demo_store()).model_validate(payload)


def test_scenario_rejects_out_of_window_reminder():
    payload = get_scenario("green-close").model_dump()
    payload["intervention"]["reminder_minute"] = payload["end_minute"] + 1
    with pytest.raises(ValidationError, match="inside the scenario window"):
        type(get_scenario("green-close")).model_validate(payload)
