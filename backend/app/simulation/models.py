from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..agents.models import AgentDecisionAudit, AgentUsageSummary


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
    AGENT_OBSERVATION = "agent_observation"
    AGENT_PROPOSAL = "agent_proposal"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_FALLBACK = "provider_fallback"
    PROVIDER_BUDGET_EXHAUSTED = "provider_budget_exhausted"
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

    @model_validator(mode="after")
    def validate_power_map(self):
        if self.state not in self.power_kw_by_state:
            raise ValueError("equipment power map must include its current state")
        if any(power < 0 for power in self.power_kw_by_state.values()):
            raise ValueError("equipment power cannot be negative")
        if self.criticality == Criticality.PROTECTED and EquipmentState.OFF in self.power_kw_by_state:
            if self.power_kw_by_state[EquipmentState.OFF] != 0:
                raise ValueError("protected equipment off-state power must be zero")
        return self

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
    floor_area_m2: float = Field(gt=0)
    opening_minute: int = Field(ge=0, lt=24 * 60)
    closing_minute: int = Field(gt=0, le=24 * 60)
    zones: list[Zone]
    equipment: list[Equipment]
    agents: list[Agent]
    customers: list[Customer] = Field(default_factory=list)
    tariff_sgd_per_kwh: float = Field(gt=0)
    grid_emission_factor_kg_per_kwh: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_references(self):
        if self.closing_minute <= self.opening_minute:
            raise ValueError("closing_minute must be after opening_minute")
        zone_ids = [zone.id for zone in self.zones]
        equipment_ids = [equipment.id for equipment in self.equipment]
        agent_ids = [agent.id for agent in self.agents]
        customer_ids = [customer.id for customer in self.customers]
        for label, identifiers in {
            "zone": zone_ids,
            "equipment": equipment_ids,
            "agent": agent_ids,
            "customer": customer_ids,
        }.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} ids must be unique")
        known_zones = set(zone_ids)
        known_equipment = set(equipment_ids)
        if any(item.zone_id not in known_zones for item in self.equipment):
            raise ValueError("every equipment item must reference a known zone")
        if any(item.zone_id not in known_zones for item in self.agents):
            raise ValueError("every staff agent must reference a known zone")
        if any(item.zone_id not in known_zones | {"exit"} for item in self.customers):
            raise ValueError("every customer agent must reference a known zone")
        if any(
            equipment_id not in known_equipment
            for agent in self.agents
            for equipment_id in agent.assigned_equipment_ids
        ):
            raise ValueError("staff assignments must reference known equipment")
        return self


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
    start_minute: int = Field(ge=0, lt=24 * 60)
    end_minute: int = Field(gt=0, le=2 * 24 * 60)
    tick_minutes: int = Field(default=1, gt=0, le=60)
    intervention: Intervention

    @model_validator(mode="after")
    def validate_timeline(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("scenario end_minute must be after start_minute")
        reminder = self.intervention.reminder_minute
        if reminder is not None and not self.start_minute <= reminder <= self.end_minute:
            raise ValueError("intervention reminder must occur inside the scenario window")
        return self


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
    agent_decisions: list[AgentDecisionAudit] = Field(default_factory=list)
    provider_usage: AgentUsageSummary = Field(default_factory=AgentUsageSummary)


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
