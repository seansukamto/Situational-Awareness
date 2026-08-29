from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..simulation.models import Store


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
    equipment_load_uncertainty_pct: float = Field(default=12, ge=0, le=75)
    tariff_uncertainty_pct: float = Field(default=5, ge=0, le=50)
    adoption_rate: float = Field(default=0.85, ge=0, le=1)


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
