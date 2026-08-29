from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..agents.models import AgentMode
from ..simulation.models import AgentRole


class AvatarDefinition(BaseModel):
    id: str
    label: str
    model_file: str
    description: str


AVATAR_CATALOG = (
    AvatarDefinition(
        id="associate",
        label="Eco Associate",
        model_file="associate.glb",
        description="A versatile frontline sustainability champion.",
    ),
    AvatarDefinition(
        id="shift-manager",
        label="Shift Captain",
        model_file="shift-manager.glb",
        description="A team lead focused on safe, coordinated action.",
    ),
    AvatarDefinition(
        id="purposeful-shopper",
        label="Purposeful Pathfinder",
        model_file="purposeful-shopper.glb",
        description="A focused character for quick task completion.",
    ),
    AvatarDefinition(
        id="value-seeker",
        label="Resource Ranger",
        model_file="value-seeker.glb",
        description="A practical character who spots avoidable waste.",
    ),
    AvatarDefinition(
        id="display-browser",
        label="Display Scout",
        model_file="display-browser.glb",
        description="An observant character for customer-facing zones.",
    ),
    AvatarDefinition(
        id="late-browser",
        label="Closing Explorer",
        model_file="late-browser.glb",
        description="A closing-shift specialist for end-of-day challenges.",
    ),
)
AVATAR_IDS = frozenset(item.id for item in AVATAR_CATALOG)


class StaffProfileCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    role: AgentRole
    avatar_id: str = Field(default="associate", min_length=1, max_length=80)
    authorized_zone_ids: list[str] = Field(default_factory=list, max_length=32)
    authorized_equipment_ids: list[str] = Field(default_factory=list, max_length=64)
    default_shift_start: int = Field(default=8 * 60, ge=0, lt=24 * 60)
    default_shift_end: int = Field(default=22 * 60, gt=0, le=24 * 60)
    join_pin: str = Field(pattern=r"^\d{4,8}$")

    @model_validator(mode="after")
    def validate_shift(self):
        if self.default_shift_end <= self.default_shift_start:
            raise ValueError("default_shift_end must be after default_shift_start")
        return self


class StaffProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    role: AgentRole | None = None
    avatar_id: str | None = Field(default=None, min_length=1, max_length=80)
    authorized_zone_ids: list[str] | None = Field(default=None, max_length=32)
    authorized_equipment_ids: list[str] | None = Field(default=None, max_length=64)
    default_shift_start: int | None = Field(default=None, ge=0, lt=24 * 60)
    default_shift_end: int | None = Field(default=None, gt=0, le=24 * 60)
    active: bool | None = None


class StaffPinReset(BaseModel):
    join_pin: str = Field(pattern=r"^\d{4,8}$")


class StaffProfile(BaseModel):
    id: str
    project_id: str
    display_name: str
    normalized_name: str
    role: AgentRole
    avatar_id: str
    authorized_zone_ids: list[str] = Field(default_factory=list)
    authorized_equipment_ids: list[str] = Field(default_factory=list)
    default_shift_start: int
    default_shift_end: int
    active: bool = True
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_shift(self):
        if self.default_shift_end <= self.default_shift_start:
            raise ValueError("default_shift_end must be after default_shift_start")
        return self


def normalize_staff_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class SustainabilityDomain(StrEnum):
    ENERGY = "energy"
    WATER = "water"
    WASTE = "waste"
    FOOD = "food"
    TRANSPORT = "transport"
    BUYING = "buying"


class VerificationMethod(StrEnum):
    SELF_CONFIRMATION = "self_confirmation"
    MANAGER = "manager"
    EQUIPMENT_QR = "equipment_qr"
    SENSOR = "sensor"


class GameDayStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    SCHEDULED = "scheduled"
    AVAILABLE = "available"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXCEPTION = "exception"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    SELF_CONFIRMED = "self_confirmed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class GameEventType(StrEnum):
    DAY_CREATED = "day_created"
    DAY_STARTED = "day_started"
    STAFF_JOINED = "staff_joined"
    TASK_RELEASED = "task_released"
    TASK_CLAIMED = "task_claimed"
    TASK_RELEASED_BY_STAFF = "task_released_by_staff"
    TASK_RESERVATION_EXPIRED = "task_reservation_expired"
    TASK_COMPLETED = "task_completed"
    TASK_EXCEPTION_REPORTED = "task_exception_reported"
    POINTS_AWARDED = "points_awarded"
    DAY_COMPLETED = "day_completed"


class TaskTemplateCreate(BaseModel):
    label: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=500)
    domain: SustainabilityDomain
    zone_id: str | None = Field(default=None, max_length=120)
    equipment_id: str | None = Field(default=None, max_length=120)
    allowed_roles: list[AgentRole] = Field(min_length=1, max_length=3)
    allowed_staff_ids: list[str] = Field(default_factory=list, max_length=64)
    available_from_minute: int = Field(default=0, ge=0, lt=24 * 60)
    available_until_minute: int = Field(default=24 * 60, gt=0, le=24 * 60)
    expected_minutes: int = Field(default=10, ge=1, le=240)
    base_points: int = Field(default=50, ge=1, le=10_000)
    maximum_points: int = Field(default=100, ge=1, le=10_000)
    verification_method: VerificationMethod = VerificationMethod.SELF_CONFIRMATION
    estimated_impact_value: float | None = Field(default=None, ge=0)
    estimated_impact_unit: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def validate_task_window_and_points(self):
        if self.available_until_minute <= self.available_from_minute:
            raise ValueError("available_until_minute must be after available_from_minute")
        if self.maximum_points < self.base_points:
            raise ValueError("maximum_points must be at least base_points")
        return self


class TaskTemplate(TaskTemplateCreate):
    id: str
    project_id: str
    active: bool = True
    created_at: datetime
    updated_at: datetime


class GameDayCreate(BaseModel):
    local_date: date | None = None
    start_minute: int | None = Field(default=None, ge=0, lt=24 * 60)
    end_minute: int | None = Field(default=None, gt=0, le=24 * 60)

    @model_validator(mode="after")
    def validate_optional_window(self):
        if (
            self.start_minute is not None
            and self.end_minute is not None
            and self.end_minute <= self.start_minute
        ):
            raise ValueError("end_minute must be after start_minute")
        return self


class GameDay(BaseModel):
    id: str
    project_id: str
    local_date: date
    timezone: str
    start_minute: int
    end_minute: int
    status: GameDayStatus
    join_token: str
    policy_version: str = "staff-game-policy-2026.08"
    scoring_version: str = "individual-points-2026.08"
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GameJoinStaff(BaseModel):
    id: str
    display_name: str
    role: AgentRole
    avatar_id: str


class GameJoinSummary(BaseModel):
    game_day_id: str
    project_id: str
    store_name: str
    local_date: date
    start_minute: int
    end_minute: int
    status: GameDayStatus
    staff: list[GameJoinStaff]


class GameJoinRequest(BaseModel):
    staff_id: str = Field(min_length=1, max_length=120)
    join_pin: str = Field(pattern=r"^\d{4,8}$")


class GameStaffSession(BaseModel):
    id: str
    game_day_id: str
    project_id: str
    staff_id: str
    created_at: datetime
    expires_at: datetime


class GameJoinResponse(BaseModel):
    session_token: str
    expires_at: datetime
    game_day: GameDay
    staff: StaffProfile


class TaskInstance(BaseModel):
    id: str
    game_day_id: str
    project_id: str
    template_id: str
    label: str
    description: str
    domain: SustainabilityDomain
    zone_id: str | None = None
    equipment_id: str | None = None
    allowed_roles: list[AgentRole]
    allowed_staff_ids: list[str] = Field(default_factory=list)
    available_from_minute: int
    available_until_minute: int
    expected_minutes: int
    base_points: int
    maximum_points: int
    verification_method: VerificationMethod
    estimated_impact_value: float | None = None
    estimated_impact_unit: str | None = None
    status: TaskStatus = TaskStatus.SCHEDULED
    claimed_by_staff_id: str | None = None
    claimed_at: datetime | None = None
    reservation_expires_at: datetime | None = None
    completed_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    points_awarded: int = 0
    scoring_version: str = "individual-points-2026.08"
    version: int = 0
    created_at: datetime
    updated_at: datetime


class TaskExceptionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=240)


class GameDayEvent(BaseModel):
    seq: int
    game_day_id: str
    occurred_at: datetime
    type: GameEventType
    message: str
    staff_id: str | None = None
    task_instance_id: str | None = None
    zone_id: str | None = None
    target_id: str | None = None
    source: Literal["staff", "manager", "rules", "ai", "sensor"]
    evidence_kind: Literal["measured", "derived", "assumed", "simulated"]
    data: dict[str, Any] = Field(default_factory=dict)


class ScoreEntry(BaseModel):
    id: str
    game_day_id: str
    project_id: str
    staff_id: str
    task_instance_id: str
    points: int
    reason: str
    scoring_version: str
    created_at: datetime


class LeaderboardEntry(BaseModel):
    rank: int
    staff_id: str
    display_name: str
    avatar_id: str
    points: int
    tasks_completed: int


GAME_LEARNING_PROMPT_VERSION = "staff-game-learning-2026.08"


class DomainPerformance(BaseModel):
    released: int = Field(ge=0)
    claimed: int = Field(ge=0)
    completed: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    estimated_impact: float = Field(ge=0)
    impact_unit: str | None = None


class GameDayLearningMetrics(BaseModel):
    active_staff_profiles: int = Field(ge=0)
    participating_staff: int = Field(ge=0)
    tasks_released: int = Field(ge=0)
    tasks_claimed: int = Field(ge=0)
    tasks_completed: int = Field(ge=0)
    tasks_released_back: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    total_points: int = Field(ge=0)
    estimated_impact_total: float = Field(ge=0)
    domain_performance: dict[SustainabilityDomain, DomainPerformance]


class GameLearningNarrative(BaseModel):
    summary: str = Field(min_length=1, max_length=700)
    patterns: list[str] = Field(default_factory=list, max_length=6)
    recommendations: list[str] = Field(default_factory=list, max_length=6)


class LearnedGamePolicy(BaseModel):
    version: str = Field(min_length=1, max_length=120)
    project_id: str
    previous_version: str | None = None
    source_game_day_id: str
    prompt_template_version: str = GAME_LEARNING_PROMPT_VERSION
    prompt_context: list[str] = Field(default_factory=list, max_length=6)
    domain_point_multipliers: dict[SustainabilityDomain, float]
    guardrails: list[str] = Field(default_factory=list, max_length=8)
    active: bool = True
    created_at: datetime

    @model_validator(mode="after")
    def validate_multipliers(self):
        for multiplier in self.domain_point_multipliers.values():
            if not 0.9 <= multiplier <= 1.1:
                raise ValueError("Domain point multipliers must remain between 0.9 and 1.1")
        return self


class GameDayAnalysis(BaseModel):
    id: str
    project_id: str
    game_day_id: str
    analyzer_mode: AgentMode
    provider: str
    model: str
    fallback_used: bool = False
    prompt_template_version: str = GAME_LEARNING_PROMPT_VERSION
    metrics: GameDayLearningMetrics
    narrative: GameLearningNarrative
    learned_policy_version: str
    created_at: datetime
