from copy import deepcopy

from .models import (
    Agent,
    AgentRole,
    AgentTraits,
    Criticality,
    Customer,
    CustomerSegment,
    Equipment,
    EquipmentState,
    Intervention,
    Position,
    Scenario,
    Store,
    Zone,
)


def build_demo_store() -> Store:
    staff_roles = {AgentRole.MANAGER, AgentRole.CLOSING_ASSOCIATE}
    zones = [
        Zone(id="checkout", label="Checkout", center=Position(x=-4, z=-2), width=4, depth=3),
        Zone(id="sales_floor", label="Sales floor", center=Position(x=0, z=1), width=6, depth=7),
        Zone(id="display_wall", label="Display wall", center=Position(x=4, z=1), width=2, depth=7),
        Zone(id="stockroom", label="Stockroom", center=Position(x=-3, z=4), width=4, depth=3),
    ]
    equipment = [
        Equipment(
            id="display_wall_lights",
            label="Display wall lighting",
            zone_id="display_wall",
            position=Position(x=4, z=0),
            state=EquipmentState.ON,
            power_kw_by_state={EquipmentState.ON: 1.2, EquipmentState.STANDBY: 0.15, EquipmentState.OFF: 0},
            criticality=Criticality.NON_CRITICAL,
            customer_facing=True,
            switchable_by_roles=staff_roles,
        ),
        Equipment(
            id="demo_displays",
            label="Product demonstration displays",
            zone_id="sales_floor",
            position=Position(x=1.5, z=2),
            state=EquipmentState.ON,
            power_kw_by_state={EquipmentState.ON: 1.8, EquipmentState.STANDBY: 0.35, EquipmentState.OFF: 0},
            criticality=Criticality.NON_CRITICAL,
            customer_facing=True,
            switchable_by_roles=staff_roles,
        ),
        Equipment(
            id="stockroom_lights",
            label="Stockroom lighting",
            zone_id="stockroom",
            position=Position(x=-3, z=4),
            state=EquipmentState.ON,
            power_kw_by_state={EquipmentState.ON: 0.6, EquipmentState.STANDBY: 0.1, EquipmentState.OFF: 0},
            criticality=Criticality.NON_CRITICAL,
            switchable_by_roles=staff_roles,
        ),
        Equipment(
            id="checkout_pos",
            label="Checkout point of sale",
            zone_id="checkout",
            position=Position(x=-4, z=-2),
            state=EquipmentState.ON,
            power_kw_by_state={EquipmentState.ON: 0.4, EquipmentState.STANDBY: 0.12, EquipmentState.OFF: 0},
            criticality=Criticality.OPERATIONAL,
            customer_facing=True,
            switchable_by_roles={AgentRole.MANAGER},
        ),
        Equipment(
            id="cold_storage",
            label="Cold storage",
            zone_id="stockroom",
            position=Position(x=-4, z=5),
            state=EquipmentState.ON,
            power_kw_by_state={EquipmentState.ON: 2.6, EquipmentState.STANDBY: 2.6, EquipmentState.OFF: 0},
            criticality=Criticality.PROTECTED,
            switchable_by_roles=set(),
        ),
    ]
    agents = [
        Agent(
            id="manager_01",
            label="Shift manager",
            role=AgentRole.MANAGER,
            zone_id="checkout",
            position=Position(x=-4, z=-2),
            assigned_equipment_ids=["checkout_pos"],
            traits=AgentTraits(
                sustainability_motivation=0.72,
                rule_compliance=0.88,
                social_susceptibility=0.45,
                fatigue_sensitivity=0.35,
                time_pressure_sensitivity=0.42,
            ),
        ),
        Agent(
            id="staff_01",
            label="Closing associate A",
            role=AgentRole.CLOSING_ASSOCIATE,
            zone_id="sales_floor",
            position=Position(x=0, z=1),
            assigned_equipment_ids=["demo_displays", "display_wall_lights"],
            traits=AgentTraits(
                sustainability_motivation=0.55,
                rule_compliance=0.68,
                social_susceptibility=0.81,
                fatigue_sensitivity=0.66,
                time_pressure_sensitivity=0.72,
            ),
        ),
        Agent(
            id="staff_02",
            label="Closing associate B",
            role=AgentRole.CLOSING_ASSOCIATE,
            zone_id="stockroom",
            position=Position(x=-3, z=4),
            assigned_equipment_ids=["stockroom_lights"],
            traits=AgentTraits(
                sustainability_motivation=0.43,
                rule_compliance=0.61,
                social_susceptibility=0.65,
                fatigue_sensitivity=0.78,
                time_pressure_sensitivity=0.69,
            ),
        ),
    ]
    customers = [
        Customer(
            id="customer_01",
            label="Purposeful shopper",
            segment=CustomerSegment.MISSION_SHOPPER,
            zone_id="sales_floor",
            position=Position(x=-1.2, z=0.8),
        ),
        Customer(
            id="customer_02",
            label="Display browser",
            segment=CustomerSegment.BROWSER,
            zone_id="display_wall",
            position=Position(x=3.4, z=1.8),
        ),
        Customer(
            id="customer_03",
            label="Value seeker",
            segment=CustomerSegment.VALUE_SEEKER,
            zone_id="sales_floor",
            position=Position(x=0.8, z=3.2),
        ),
        Customer(
            id="customer_04",
            label="Late browser",
            segment=CustomerSegment.BROWSER,
            zone_id="display_wall",
            position=Position(x=3.6, z=-0.4),
        ),
    ]
    return Store(
        id="store_demo_01",
        name="Situational Awareness Demo Store",
        floor_area_m2=180,
        opening_minute=8 * 60,
        closing_minute=22 * 60,
        zones=zones,
        equipment=equipment,
        agents=agents,
        customers=customers,
        tariff_sgd_per_kwh=0.3191,
        grid_emission_factor_kg_per_kwh=0.402,
    )


SCENARIOS = {
    "baseline": Scenario(
        id="baseline",
        label="Current closing routine",
        description="No assigned zones or contextual team feedback.",
        start_minute=21 * 60 + 30,
        end_minute=22 * 60 + 30,
        tick_minutes=5,
        intervention=Intervention(id="none", label="No intervention", kind="baseline"),
    ),
    "green-close": Scenario(
        id="green-close",
        label="Green Close",
        description="Assigned shutdown zones with a timely team reminder and manager support.",
        start_minute=21 * 60 + 30,
        end_minute=22 * 60 + 30,
        tick_minutes=5,
        intervention=Intervention(
            id="assigned-zone-team-feedback",
            label="Assigned zones and team feedback",
            kind="assigned_zone_team_feedback",
            reminder_minute=21 * 60 + 50,
            clarity=0.85,
            social_norm_strength=0.65,
            manager_support=0.8,
        ),
    ),
}


def get_scenario(scenario_id: str) -> Scenario:
    try:
        return deepcopy(SCENARIOS[scenario_id])
    except KeyError as exc:
        raise ValueError(f"Unknown scenario: {scenario_id}") from exc


def list_scenarios() -> list[Scenario]:
    return [deepcopy(item) for item in SCENARIOS.values()]
