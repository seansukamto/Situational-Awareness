from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..simulation.models import EventExplanation, ScenarioComparison, Store


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvidenceKind(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    ASSUMED = "assumed"
    SIMULATED = "simulated"


class BillStatus(StrEnum):
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"


class ScenarioSettings(BaseModel):
    scenario_id: Literal["green-close"] = "green-close"
    operating_days_per_year: int = Field(default=360, ge=1, le=366)
    labour_cost_sgd_per_hour: float = Field(default=16.5, ge=0, le=250)
    annual_revenue_sgd: float = Field(default=1_500_000, gt=0, le=10_000_000_000)
    equipment_load_uncertainty_pct: float = Field(default=12, ge=0, le=75)
    tariff_uncertainty_pct: float = Field(default=5, ge=0, le=50)
    adoption_rate: float = Field(default=0.85, ge=0, le=1)


class StoreSettings(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(min_length=3, max_length=64)
    floor_area_m2: float = Field(gt=0, le=1_000_000)
    opening_minute: int = Field(ge=0, lt=24 * 60)
    closing_minute: int = Field(gt=0, le=24 * 60)
    tariff_sgd_per_kwh: float = Field(gt=0, le=100)
    grid_emission_factor_kg_per_kwh: float = Field(ge=0, le=10)

    @model_validator(mode="after")
    def closing_is_after_opening(self):
        if self.closing_minute <= self.opening_minute:
            raise ValueError("closing_minute must be after opening_minute")
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    store: Store
    settings: ScenarioSettings = Field(default_factory=ScenarioSettings)


class Project(ProjectCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class EvidenceField(BaseModel):
    field: str
    value: str | float
    unit: str | None = None
    kind: EvidenceKind
    source: str
    confidence: float = Field(ge=0, le=1)


class UtilityBillDraft(BaseModel):
    filename: str
    period_start: str
    period_end: str
    total_kwh: float = Field(gt=0)
    total_cost_sgd: float = Field(gt=0)
    account_label: str = "Store electricity account"
    evidence: list[EvidenceField] = Field(default_factory=list)

    @model_validator(mode="after")
    def period_is_ordered(self):
        try:
            period_start = date.fromisoformat(self.period_start)
            period_end = date.fromisoformat(self.period_end)
        except ValueError as exc:
            raise ValueError("bill period dates must use YYYY-MM-DD") from exc
        if period_end < period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class UtilityBill(UtilityBillDraft):
    id: str
    project_id: str
    status: BillStatus
    average_tariff_sgd_per_kwh: float
    raw_file_retained: bool = False
    created_at: datetime
    confirmed_at: datetime | None = None


class BillConfirmation(BaseModel):
    period_start: str
    period_end: str
    total_kwh: float = Field(gt=0)
    total_cost_sgd: float = Field(gt=0)


class AnalysisRequest(BaseModel):
    samples: int = Field(default=120, ge=25, le=500)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class Distribution(BaseModel):
    label: str
    unit: str
    p10: float
    p50: float
    p90: float
    mean: float
    evidence_kind: EvidenceKind
    interpretation: str


class ImpactAssumption(BaseModel):
    id: str
    label: str
    value: float | str
    unit: str | None = None
    kind: EvidenceKind
    source: str
    editable: bool


class ImpactAnalysis(BaseModel):
    id: str
    project_id: str
    scenario_id: str
    sample_count: int
    seed: int
    generated_at: datetime
    bill_id: str
    metrics: dict[str, Distribution]
    assumptions: list[ImpactAssumption]
    risks: list[str]
    calibration: dict[str, Any]


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationRunCreate(BaseModel):
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    sample_count: int = Field(default=120, ge=25, le=500)


class GameMasterRuleSnapshot(BaseModel):
    id: str
    label: str
    description: str


class PersistedSimulationRun(BaseModel):
    id: str
    project_id: str
    created_at: datetime
    completed_at: datetime | None = None
    status: RunStatus
    seed: int
    sample_count: int
    comparison: ScenarioComparison | None = None
    impact_analysis: ImpactAnalysis | None = None
    store_snapshot: Store
    scenario_settings_snapshot: ScenarioSettings
    evidence_snapshot: UtilityBill | None = None
    baseline_explanations: list[EventExplanation] = Field(default_factory=list)
    intervention_explanations: list[EventExplanation] = Field(default_factory=list)
    configuration_hash: str
    configuration_current: bool = True
    game_master_rules_version: str
    game_master_rules_snapshot: list[GameMasterRuleSnapshot] = Field(default_factory=list)
    failure_message: str | None = None


class SimulationRunSummary(BaseModel):
    id: str
    project_id: str
    created_at: datetime
    completed_at: datetime | None = None
    status: RunStatus
    seed: int
    sample_count: int
    estimated_savings_sgd: float | None = None
    configuration_current: bool
    game_master_rules_version: str
    failure_message: str | None = None


class ChecklistTask(BaseModel):
    id: str
    equipment_id: str
    label: str
    zone_label: str
    assigned_role: str
    criticality: str
    completed_at: datetime | None = None


class ChecklistSession(BaseModel):
    id: str
    token: str
    project_id: str
    store_name: str
    scenario_label: str = "Green Close"
    status: str = "open"
    tasks: list[ChecklistTask]
    safety_note: str
    created_at: datetime
    expires_at: datetime


class ChecklistCompletion(BaseModel):
    task_id: str
    completed: bool
