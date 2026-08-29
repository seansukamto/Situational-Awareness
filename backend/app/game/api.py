from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..projects.models import Project
from ..projects.repository import SQLiteRepository
from .models import (
    AVATAR_CATALOG,
    AVATAR_IDS,
    AvatarDefinition,
    StaffPinReset,
    StaffProfile,
    StaffProfileCreate,
    StaffProfileUpdate,
    normalize_staff_name,
)
from .security import hash_staff_pin


router = APIRouter(prefix="/api", tags=["staff game"])


def repository(request: Request) -> SQLiteRepository:
    return request.app.state.repository


def require_project(repo: SQLiteRepository, project_id: str) -> Project:
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_staff(
    repo: SQLiteRepository,
    project_id: str,
    staff_id: str,
) -> StaffProfile:
    profile = repo.get_staff_profile(project_id, staff_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Staff profile not found")
    return profile


def validate_staff_configuration(
    project: Project,
    *,
    avatar_id: str,
    zone_ids: list[str],
    equipment_ids: list[str],
) -> None:
    if avatar_id not in AVATAR_IDS:
        raise HTTPException(status_code=422, detail="Unknown staff avatar")
    known_zones = {item.id for item in project.store.zones}
    unknown_zones = sorted(set(zone_ids) - known_zones)
    if unknown_zones:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown authorized zones: {', '.join(unknown_zones)}",
        )
    known_equipment = {item.id for item in project.store.equipment}
    unknown_equipment = sorted(set(equipment_ids) - known_equipment)
    if unknown_equipment:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown authorized equipment: {', '.join(unknown_equipment)}",
        )


def clean_staff_name(value: str) -> tuple[str, str]:
    display_name = " ".join(value.strip().split())
    normalized_name = normalize_staff_name(value)
    if len(normalized_name) < 2:
        raise HTTPException(status_code=422, detail="Staff name is too short")
    return display_name, normalized_name


@router.get("/avatars", response_model=list[AvatarDefinition])
def list_avatars() -> list[AvatarDefinition]:
    return list(AVATAR_CATALOG)


@router.get(
    "/projects/{project_id}/staff",
    response_model=list[StaffProfile],
)
def list_staff(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[StaffProfile]:
    require_project(repo, project_id)
    return repo.list_staff_profiles(project_id)


@router.post(
    "/projects/{project_id}/staff",
    response_model=StaffProfile,
    status_code=status.HTTP_201_CREATED,
)
def create_staff(
    project_id: str,
    payload: StaffProfileCreate,
    repo: SQLiteRepository = Depends(repository),
) -> StaffProfile:
    project = require_project(repo, project_id)
    validate_staff_configuration(
        project,
        avatar_id=payload.avatar_id,
        zone_ids=payload.authorized_zone_ids,
        equipment_ids=payload.authorized_equipment_ids,
    )
    now = datetime.now(UTC)
    display_name, normalized_name = clean_staff_name(payload.display_name)
    profile = StaffProfile(
        id=f"staff_{uuid4().hex[:12]}",
        project_id=project_id,
        display_name=display_name,
        normalized_name=normalized_name,
        role=payload.role,
        avatar_id=payload.avatar_id,
        authorized_zone_ids=list(dict.fromkeys(payload.authorized_zone_ids)),
        authorized_equipment_ids=list(
            dict.fromkeys(payload.authorized_equipment_ids)
        ),
        default_shift_start=payload.default_shift_start,
        default_shift_end=payload.default_shift_end,
        created_at=now,
        updated_at=now,
    )
    pin_salt, pin_hash = hash_staff_pin(payload.join_pin)
    try:
        return repo.create_staff_profile(profile, pin_salt, pin_hash)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A staff profile with this name already exists",
        ) from exc


@router.put(
    "/projects/{project_id}/staff/{staff_id}",
    response_model=StaffProfile,
)
def update_staff(
    project_id: str,
    staff_id: str,
    payload: StaffProfileUpdate,
    repo: SQLiteRepository = Depends(repository),
) -> StaffProfile:
    project = require_project(repo, project_id)
    current = require_staff(repo, project_id, staff_id)
    updates = payload.model_dump(exclude_none=True)
    display_name = updates.pop("display_name", current.display_name)
    cleaned_display_name, normalized_name = clean_staff_name(display_name)
    updated = current.model_copy(
        update={
            **updates,
            "display_name": cleaned_display_name,
            "normalized_name": normalized_name,
            "updated_at": datetime.now(UTC),
        }
    )
    validate_staff_configuration(
        project,
        avatar_id=updated.avatar_id,
        zone_ids=updated.authorized_zone_ids,
        equipment_ids=updated.authorized_equipment_ids,
    )
    if updated.default_shift_end <= updated.default_shift_start:
        raise HTTPException(
            status_code=422,
            detail="default_shift_end must be after default_shift_start",
        )
    try:
        saved = repo.update_staff_profile(updated)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A staff profile with this name already exists",
        ) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="Staff profile not found")
    return saved


@router.post(
    "/projects/{project_id}/staff/{staff_id}/reset-pin",
    response_model=StaffProfile,
)
def reset_staff_pin(
    project_id: str,
    staff_id: str,
    payload: StaffPinReset,
    repo: SQLiteRepository = Depends(repository),
) -> StaffProfile:
    require_project(repo, project_id)
    profile = require_staff(repo, project_id, staff_id)
    pin_salt, pin_hash = hash_staff_pin(payload.join_pin)
    updated = repo.update_staff_pin(project_id, staff_id, pin_salt, pin_hash)
    assert updated is not None
    return updated
