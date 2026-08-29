from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EquipmentState(StrEnum):
    ON = "on"
    STANDBY = "standby"
    OFF = "off"


class Criticality(StrEnum):
    NON_CRITICAL = "non_critical"
    OPERATIONAL = "operational"
    PROTECTED = "protected"


class AgentRole(StrEnum):
    MANAGER = "manager"
    CLOSING_ASSOCIATE = "closing_associate"
    CASHIER = "cashier"


class CustomerSegment(StrEnum):
    BROWSER = "browser"
    MISSION_SHOPPER = "mission_shopper"
    VALUE_SEEKER = "value_seeker"


class ActionType(StrEnum):
    MOVE_TO = "move_to"
    TOGGLE_EQUIPMENT = "toggle_equipment"
    COMPLETE_CHECKLIST = "complete_checklist"
    REPORT_EXCEPTION = "report_exception"
    END_SHIFT = "end_shift"


class EventType(StrEnum):
    SIMULATION_STARTED = "simulation_started"
    STORE_CLOSED = "store_closed"
    CUSTOMER_COUNT_CHANGED = "customer_count_changed"
    CUSTOMER_MOVED = "customer_moved"
    CUSTOMER_EXITED = "customer_exited"
    NUDGE_SENT = "nudge_sent"
    AGENT_MOVED = "agent_moved"
    ACTION_ACCEPTED = "action_accepted"
    ACTION_REJECTED = "action_rejected"
    EQUIPMENT_STATE_CHANGED = "equipment_state_changed"
    CHECKLIST_COMPLETED = "checklist_completed"
    SHIFT_ENDED = "shift_ended"
    SIMULATION_COMPLETED = "simulation_completed"


class Position(BaseModel):
    x: float
    z: float


class Zone(BaseModel):
    id: str
    label: str
    center: Position
    width: float
    depth: float


class Equipment(BaseModel):
    id: str
    label: str
    zone_id: str
    position: Position
    state: EquipmentState
    power_kw_by_state: dict[EquipmentState, float]
    criticality: Criticality
    customer_facing: bool = False
    switchable_by_roles: set[AgentRole] = Field(default_factory=set)

    def power_kw(self) -> float:
        return self.power_kw_by_state[self.state]


class AgentTraits(BaseModel):
    sustainability_motivation: float = Field(ge=0, le=1)
    rule_compliance: float = Field(ge=0, le=1)
    social_susceptibility: float = Field(ge=0, le=1)
    fatigue_sensitivity: float = Field(ge=0, le=1)
    time_pressure_sensitivity: float = Field(ge=0, le=1)


class Agent(BaseModel):
    id: str
    label: str
    role: AgentRole
    zone_id: str
    position: Position
    assigned_equipment_ids: list[str] = Field(default_factory=list)
    traits: AgentTraits
    fatigue: float = Field(default=0.25, ge=0, le=1)
    workload: float = Field(default=0.4, ge=0, le=1)
    minutes_spent_on_intervention: float = 0
    checklist_completed: bool = False
    shift_ended: bool = False


class Customer(BaseModel):
    id: str
    label: str
    segment: CustomerSegment
    zone_id: str
    position: Position
    active: bool = True
    satisfaction: float = Field(default=0.85, ge=0, le=1)


class Store(BaseModel):
    id: str
    name: str
    timezone: str = "Asia/Singapore"
    floor_area_m2: float
    opening_minute: int
    closing_minute: int
    zones: list[Zone]
    equipment: list[Equipment]
    agents: list[Agent]
    customers: list[Customer] = Field(default_factory=list)
    tariff_sgd_per_kwh: float
    grid_emission_factor_kg_per_kwh: float


class Intervention(BaseModel):
    id: str
    label: str
    kind: Literal["baseline", "assigned_zone_team_feedback"]
    reminder_minute: int | None = None
    clarity: float = Field(default=0, ge=0, le=1)
    social_norm_strength: float = Field(default=0, ge=0, le=1)
    manager_support: float = Field(default=0, ge=0, le=1)


class Scenario(BaseModel):
    id: str
    label: str
    description: str
    start_minute: int
    end_minute: int
    tick_minutes: int = 1
    intervention: Intervention


class ActionProposal(BaseModel):
    agent_id: str
    action: ActionType
    target_id: str | None = None
    desired_state: EquipmentState | None = None
    reason_code: str


class SimulationEvent(BaseModel):
    seq: int
    at_minute: int
    type: EventType
    message: str
    agent_id: str | None = None
    target_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventExplanation(BaseModel):
    event_seq: int
    summary: str
    rationale: str
    rules_checked: list[str]
    grounded_in: list[str]
    counterfactual: str
    confidence: Literal["high", "medium"]


class RunMetrics(BaseModel):
    total_kwh: float
    after_hours_kwh: float
    cost_sgd: float
    emissions_kg_co2: float
    shutdown_tasks_total: int
    shutdown_tasks_completed: int
    completion_rate: float
    staff_minutes: float
    overtime_minutes: float
    rejected_actions: int
    customer_service_incidents: int


class SimulationRun(BaseModel):
    id: str
    scenario_id: str
    seed: int
    store: Store
    events: list[SimulationEvent]
    metrics: RunMetrics


class ComparisonMetric(BaseModel):
    baseline: float
    intervention: float
    difference: float
    percent_change: float | None


class ScenarioComparison(BaseModel):
    baseline_run: SimulationRun
    intervention_run: SimulationRun
    energy_kwh: ComparisonMetric
    cost_sgd: ComparisonMetric
    emissions_kg_co2: ComparisonMetric
    completion_rate: ComparisonMetric
