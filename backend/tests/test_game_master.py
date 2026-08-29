from app.simulation import GameMaster, build_demo_store, get_scenario
from app.simulation.models import ActionProposal, ActionType, EquipmentState, EventType


def test_identical_seed_produces_replayable_run():
    first = GameMaster(build_demo_store(), get_scenario("green-close"), 91).run()
    second = GameMaster(build_demo_store(), get_scenario("green-close"), 91).run()
    assert first.model_dump() == second.model_dump()


def test_game_master_protects_cold_storage():
    master = GameMaster(build_demo_store(), get_scenario("green-close"), 42)
    proposal = ActionProposal(
        agent_id="manager_01",
        action=ActionType.TOGGLE_EQUIPMENT,
        target_id="cold_storage",
        desired_state=EquipmentState.OFF,
        reason_code="test",
    )
    accepted, reason = master._validate(proposal)
    assert accepted is False
    assert "protected" in reason


def test_customer_facing_equipment_stays_on_while_customers_remain():
    master = GameMaster(build_demo_store(), get_scenario("green-close"), 42)
    master.customer_count = 2
    proposal = ActionProposal(
        agent_id="staff_01",
        action=ActionType.TOGGLE_EQUIPMENT,
        target_id="display_wall_lights",
        desired_state=EquipmentState.OFF,
        reason_code="test",
    )
    accepted, reason = master._validate(proposal)
    assert accepted is False
    assert "customers" in reason


def test_green_close_improves_expected_completion_across_seeds():
    baseline_completed = 0
    intervention_completed = 0
    baseline_energy = 0.0
    intervention_energy = 0.0
    for seed in range(50):
        baseline = GameMaster(build_demo_store(), get_scenario("baseline"), seed).run()
        intervention = GameMaster(build_demo_store(), get_scenario("green-close"), seed).run()
        baseline_completed += baseline.metrics.shutdown_tasks_completed
        intervention_completed += intervention.metrics.shutdown_tasks_completed
        baseline_energy += baseline.metrics.after_hours_kwh
        intervention_energy += intervention.metrics.after_hours_kwh
    assert intervention_completed > baseline_completed
    assert intervention_energy < baseline_energy


def test_run_has_contiguous_event_sequence_and_metrics_event():
    run = GameMaster(build_demo_store(), get_scenario("green-close"), 7).run()
    assert [event.seq for event in run.events] == list(range(1, len(run.events) + 1))
    assert run.events[-1].type == EventType.SIMULATION_COMPLETED
    assert run.events[-1].data["metrics"] == run.metrics.model_dump(mode="json")


def test_customer_agents_move_and_exit_before_shutdown():
    run = GameMaster(build_demo_store(), get_scenario("green-close"), 7).run()
    customer_events = [
        event
        for event in run.events
        if event.type in {EventType.CUSTOMER_MOVED, EventType.CUSTOMER_EXITED}
    ]
    assert customer_events
    assert all(not customer.active for customer in run.store.customers)
    assert any(event.type == EventType.CUSTOMER_EXITED for event in customer_events)


def test_completion_metrics_use_every_authorized_assigned_task():
    run = GameMaster(build_demo_store(), get_scenario("green-close"), 42).run()
    completed_targets = {
        event.target_id
        for event in run.events
        if event.type == EventType.EQUIPMENT_STATE_CHANGED
    }
    assert run.metrics.shutdown_tasks_total == 4
    assert run.metrics.shutdown_tasks_completed == len(completed_targets)
    assert "cold_storage" not in completed_targets
