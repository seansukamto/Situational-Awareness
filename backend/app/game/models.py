from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

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
