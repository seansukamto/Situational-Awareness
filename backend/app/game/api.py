from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..projects.models import Project
from ..projects.repository import SQLiteRepository
from .analysis import analyze_game_day
from .models import (
    AVATAR_CATALOG,
    AVATAR_IDS,
    AvatarDefinition,
    GameDay,
    GameDayAnalysis,
    GameDayCreate,
    GameDayEvent,
    GameDayStatus,
    GameEventType,
    GameJoinRequest,
    GameJoinResponse,
    GameJoinStaff,
    GameJoinSummary,
    GameStaffSession,
    LeaderboardEntry,
    LearnedGamePolicy,
    StaffPinReset,
    StaffProfile,
    StaffProfileCreate,
    StaffProfileUpdate,
    TaskInstance,
    TaskStatus,
    TaskTemplate,
    TaskTemplateCreate,
    VerificationStatus,
    normalize_staff_name,
)
from .scoring import SCORING_VERSION, local_minute, score_completed_task
from .security import hash_session_token, hash_staff_pin


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


def validate_task_template(
    repo: SQLiteRepository,
    project: Project,
    payload: TaskTemplateCreate,
) -> None:
    known_zones = {item.id for item in project.store.zones}
    if payload.zone_id and payload.zone_id not in known_zones:
        raise HTTPException(status_code=422, detail="Unknown task zone")
    known_staff = {item.id for item in repo.list_staff_profiles(project.id)}
    unknown_staff = sorted(set(payload.allowed_staff_ids) - known_staff)
    if unknown_staff:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown allowed staff: {', '.join(unknown_staff)}",
        )
    if payload.equipment_id is None:
        return
    equipment = next(
        (item for item in project.store.equipment if item.id == payload.equipment_id),
        None,
    )
    if equipment is None:
        raise HTTPException(status_code=422, detail="Unknown task equipment")
    if payload.zone_id != equipment.zone_id:
        raise HTTPException(
            status_code=422,
            detail="Equipment tasks must use the equipment's authoritative zone",
        )
    if str(equipment.criticality) == "protected":
        raise HTTPException(
            status_code=422,
            detail="Protected equipment cannot become a game task",
        )
    unauthorized_roles = [
        role for role in payload.allowed_roles if role not in equipment.switchable_by_roles
    ]
    if unauthorized_roles:
        raise HTTPException(
            status_code=422,
            detail="Task roles must be authorized to operate the selected equipment",
        )


@router.get(
    "/projects/{project_id}/task-templates",
    response_model=list[TaskTemplate],
)
def list_task_templates(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[TaskTemplate]:
    require_project(repo, project_id)
    return repo.list_task_templates(project_id)


@router.post(
    "/projects/{project_id}/task-templates",
    response_model=TaskTemplate,
    status_code=status.HTTP_201_CREATED,
)
def create_task_template(
    project_id: str,
    payload: TaskTemplateCreate,
    repo: SQLiteRepository = Depends(repository),
) -> TaskTemplate:
    project = require_project(repo, project_id)
    validate_task_template(repo, project, payload)
    now = datetime.now(UTC)
    template = TaskTemplate(
        id=f"template_{uuid4().hex[:12]}",
        project_id=project_id,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    return repo.create_task_template(template)


def require_game_day(
    repo: SQLiteRepository,
    project_id: str,
    game_day_id: str,
) -> GameDay:
    game_day = repo.get_game_day(project_id, game_day_id)
    if game_day is None:
        raise HTTPException(status_code=404, detail="Game day not found")
    return game_day


@router.post(
    "/projects/{project_id}/game-days",
    response_model=GameDay,
    status_code=status.HTTP_201_CREATED,
)
def create_game_day(
    project_id: str,
    payload: GameDayCreate,
    repo: SQLiteRepository = Depends(repository),
) -> GameDay:
    project = require_project(repo, project_id)
    now = datetime.now(UTC)
    localized = now.astimezone(ZoneInfo(project.store.timezone))
    start_minute = (
        payload.start_minute
        if payload.start_minute is not None
        else project.store.opening_minute
    )
    end_minute = (
        payload.end_minute
        if payload.end_minute is not None
        else project.store.closing_minute
    )
    if end_minute <= start_minute:
        raise HTTPException(status_code=422, detail="Game day end must be after start")
    learned_policy = repo.get_active_game_policy(project_id)
    game_day = GameDay(
        id=f"day_{uuid4().hex[:12]}",
        project_id=project_id,
        local_date=payload.local_date or localized.date(),
        timezone=project.store.timezone,
        start_minute=start_minute,
        end_minute=end_minute,
        status=GameDayStatus.SCHEDULED,
        join_token=secrets.token_urlsafe(18),
        policy_version=learned_policy.version if learned_policy else "staff-game-policy-2026.08",
        created_at=now,
    )
    try:
        return repo.create_game_day(game_day)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A game day already exists for this project and date",
        ) from exc


@router.get(
    "/projects/{project_id}/game-days",
    response_model=list[GameDay],
)
def list_game_days(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[GameDay]:
    require_project(repo, project_id)
    return repo.list_game_days(project_id)


@router.get(
    "/projects/{project_id}/game-days/{game_day_id}",
    response_model=GameDay,
)
def get_game_day(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> GameDay:
    require_project(repo, project_id)
    return require_game_day(repo, project_id, game_day_id)


@router.post(
    "/projects/{project_id}/game-days/{game_day_id}/start",
    response_model=GameDay,
)
def start_game_day(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> GameDay:
    require_project(repo, project_id)
    game_day = require_game_day(repo, project_id, game_day_id)
    if game_day.status == GameDayStatus.ACTIVE:
        return game_day
    if game_day.status != GameDayStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail="Only a scheduled game day can start")
    now = datetime.now(UTC)
    templates = repo.list_task_templates(project_id, active_only=True)
    learned_policy = repo.get_game_policy(project_id, game_day.policy_version)
    tasks = [
        TaskInstance(
            id=f"task_{uuid4().hex[:12]}",
            game_day_id=game_day.id,
            project_id=project_id,
            template_id=template.id,
            label=template.label,
            description=template.description,
            domain=template.domain,
            zone_id=template.zone_id,
            equipment_id=template.equipment_id,
            allowed_roles=template.allowed_roles,
            allowed_staff_ids=template.allowed_staff_ids,
            available_from_minute=template.available_from_minute,
            available_until_minute=template.available_until_minute,
            expected_minutes=template.expected_minutes,
            base_points=max(1, round(template.base_points * (
                learned_policy.domain_point_multipliers.get(template.domain, 1.0)
                if learned_policy else 1.0
            ))),
            maximum_points=max(1, round(template.maximum_points * (
                learned_policy.domain_point_multipliers.get(template.domain, 1.0)
                if learned_policy else 1.0
            ))),
            verification_method=template.verification_method,
            estimated_impact_value=template.estimated_impact_value,
            estimated_impact_unit=template.estimated_impact_unit,
            status=TaskStatus.AVAILABLE,
            scoring_version=game_day.scoring_version,
            created_at=now,
            updated_at=now,
        )
        for template in templates
    ]
    if tasks:
        repo.create_task_instances(tasks)
    started = game_day.model_copy(
        update={"status": GameDayStatus.ACTIVE, "started_at": now}
    )
    repo.update_game_day(started)
    repo.append_game_event(
        GameDayEvent(
            seq=0,
            game_day_id=game_day.id,
            occurred_at=now,
            type=GameEventType.DAY_STARTED,
            message="The staff sustainability game started.",
            source="manager",
            evidence_kind="measured",
            data={
                "task_count": len(tasks),
                "policy_version": game_day.policy_version,
                "learned_prompt_context": learned_policy.prompt_context if learned_policy else [],
            },
        )
    )
    return started


def ensure_game_day_analysis(
    repo: SQLiteRepository,
    project: Project,
    game_day: GameDay,
) -> GameDayAnalysis:
    existing = repo.get_game_day_analysis(project.id, game_day.id)
    if existing is not None:
        return existing
    analysis, policy = analyze_game_day(
        project,
        game_day,
        repo.list_task_instances(game_day.id),
        repo.list_game_day_events(game_day.id),
        repo.list_staff_profiles(project.id),
        repo.get_active_game_policy(project.id),
    )
    stored, _ = repo.save_game_learning(analysis, policy)
    return stored


@router.post(
    "/projects/{project_id}/game-days/{game_day_id}/close",
    response_model=GameDay,
)
def close_game_day(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> GameDay:
    project = require_project(repo, project_id)
    game_day = require_game_day(repo, project_id, game_day_id)
    if game_day.status == GameDayStatus.COMPLETED:
        ensure_game_day_analysis(repo, project, game_day)
        return game_day
    if game_day.status != GameDayStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Only an active game day can close")
    now = datetime.now(UTC)
    completed = game_day.model_copy(
        update={"status": GameDayStatus.COMPLETED, "completed_at": now}
    )
    repo.update_game_day(completed)
    repo.append_game_event(
        GameDayEvent(
            seq=0,
            game_day_id=game_day.id,
            occurred_at=now,
            type=GameEventType.DAY_COMPLETED,
            message="The staff sustainability game day ended.",
            source="manager",
            evidence_kind="measured",
        )
    )
    ensure_game_day_analysis(repo, project, completed)
    return completed


@router.get(
    "/projects/{project_id}/game-days/{game_day_id}/analysis",
    response_model=GameDayAnalysis,
)
def get_game_day_analysis(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> GameDayAnalysis:
    require_project(repo, project_id)
    require_game_day(repo, project_id, game_day_id)
    analysis = repo.get_game_day_analysis(project_id, game_day_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Game day analysis is not available until close")
    return analysis


@router.get(
    "/projects/{project_id}/game-policies",
    response_model=list[LearnedGamePolicy],
)
def list_game_policies(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[LearnedGamePolicy]:
    require_project(repo, project_id)
    return repo.list_game_policies(project_id)


def game_join_summary(
    repo: SQLiteRepository,
    game_day: GameDay,
) -> GameJoinSummary:
    project = require_project(repo, game_day.project_id)
    staff = [
        GameJoinStaff(
            id=item.id,
            display_name=item.display_name,
            role=item.role,
            avatar_id=item.avatar_id,
        )
        for item in repo.list_staff_profiles(game_day.project_id)
        if item.active
    ]
    return GameJoinSummary(
        game_day_id=game_day.id,
        project_id=game_day.project_id,
        store_name=project.name,
        local_date=game_day.local_date,
        start_minute=game_day.start_minute,
        end_minute=game_day.end_minute,
        status=game_day.status,
        staff=staff,
    )


@router.get("/game/join/{join_token}", response_model=GameJoinSummary)
def inspect_game_join(
    join_token: str,
    repo: SQLiteRepository = Depends(repository),
) -> GameJoinSummary:
    game_day = repo.get_game_day_by_join_token(join_token)
    if game_day is None:
        raise HTTPException(status_code=404, detail="Game day link not found")
    return game_join_summary(repo, game_day)


@router.post("/game/join/{join_token}", response_model=GameJoinResponse)
def join_game(
    join_token: str,
    payload: GameJoinRequest,
    repo: SQLiteRepository = Depends(repository),
) -> GameJoinResponse:
    game_day = repo.get_game_day_by_join_token(join_token)
    if game_day is None:
        raise HTTPException(status_code=404, detail="Game day link not found")
    if game_day.status != GameDayStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="This game day is not active")
    staff = require_staff(repo, game_day.project_id, payload.staff_id)
    if not staff.active or not repo.verify_staff_pin(
        game_day.project_id,
        staff.id,
        payload.join_pin,
    ):
        raise HTTPException(status_code=401, detail="Staff name or PIN is incorrect")
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    local_midnight = datetime.combine(
        game_day.local_date,
        time.min,
        tzinfo=ZoneInfo(game_day.timezone),
    )
    expires_at = (local_midnight + timedelta(minutes=game_day.end_minute + 120)).astimezone(UTC)
    if expires_at <= now:
        expires_at = now + timedelta(hours=2)
    session = GameStaffSession(
        id=f"session_{uuid4().hex[:12]}",
        game_day_id=game_day.id,
        project_id=game_day.project_id,
        staff_id=staff.id,
        created_at=now,
        expires_at=expires_at,
    )
    repo.create_game_session(session, hash_session_token(raw_token))
    return GameJoinResponse(
        session_token=raw_token,
        expires_at=expires_at,
        game_day=game_day,
        staff=staff,
    )


@dataclass(frozen=True)
class GameContext:
    repo: SQLiteRepository
    session: GameStaffSession
    game_day: GameDay
    project: Project
    staff: StaffProfile


def require_game_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> GameContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Staff game session required")
    raw_token = authorization.removeprefix("Bearer ").strip()
    repo: SQLiteRepository = request.app.state.repository
    session = repo.get_game_session_by_token_hash(hash_session_token(raw_token))
    now = datetime.now(UTC)
    if session is None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Staff game session expired")
    game_day = require_game_day(repo, session.project_id, session.game_day_id)
    project = require_project(repo, session.project_id)
    staff = require_staff(repo, session.project_id, session.staff_id)
    return GameContext(
        repo=repo,
        session=session,
        game_day=game_day,
        project=project,
        staff=staff,
    )


def staff_can_take_task(context: GameContext, task: TaskInstance) -> bool:
    staff = context.staff
    if staff.role not in task.allowed_roles:
        return False
    if task.allowed_staff_ids and staff.id not in task.allowed_staff_ids:
        return False
    if staff.authorized_zone_ids and task.zone_id not in staff.authorized_zone_ids:
        return False
    if (
        staff.authorized_equipment_ids
        and task.equipment_id
        and task.equipment_id not in staff.authorized_equipment_ids
    ):
        return False
    return True


def task_is_inside_window(context: GameContext, task: TaskInstance, now: datetime) -> bool:
    minute = local_minute(now, context.game_day.timezone)
    return task.available_from_minute <= minute <= task.available_until_minute


def require_staff_task(
    context: GameContext,
    task_id: str,
) -> TaskInstance:
    task = context.repo.get_task_instance(context.game_day.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Game task not found")
    return task


@router.get("/game/tasks", response_model=list[TaskInstance])
def list_game_tasks(
    context: GameContext = Depends(require_game_context),
) -> list[TaskInstance]:
    now = datetime.now(UTC)
    visible: list[TaskInstance] = []
    for task in context.repo.list_task_instances(context.game_day.id):
        if task.claimed_by_staff_id == context.staff.id:
            visible.append(task)
        elif (
            task.status == TaskStatus.AVAILABLE
            and staff_can_take_task(context, task)
            and task_is_inside_window(context, task, now)
        ):
            visible.append(task)
    available = [task for task in visible if task.status == TaskStatus.AVAILABLE]
    learned_policy = context.repo.get_game_policy(
        context.project.id,
        context.game_day.policy_version,
    )
    preferences = (
        learned_policy.staff_domain_preferences.get(context.staff.id, [])
        if learned_policy else []
    )
    recommended_id: str | None = None
    recommendation_reason: str | None = None
    if available:
        def recommendation_rank(task: TaskInstance) -> tuple[int, float, float, int]:
            preference = (
                len(preferences) - preferences.index(task.domain)
                if task.domain in preferences else 0
            )
            multiplier = (
                learned_policy.domain_point_multipliers.get(task.domain, 1.0)
                if learned_policy else 1.0
            )
            return preference, multiplier, task.estimated_impact_value or 0, task.base_points

        recommended = max(available, key=recommendation_rank)
        recommended_id = recommended.id
        if recommended.domain in preferences:
            recommendation_reason = (
                f"Matches your successful {recommended.domain} challenge history."
            )
        elif learned_policy and learned_policy.domain_point_multipliers.get(recommended.domain, 1.0) > 1:
            recommendation_reason = (
                f"Prior-day analysis prioritized a clearer {recommended.domain} challenge."
            )
        else:
            recommendation_reason = "Highest-impact eligible challenge currently available."
    enriched = [
        task.model_copy(update={
            "game_master_recommended": task.id == recommended_id,
            "recommendation_reason": recommendation_reason if task.id == recommended_id else None,
        })
        for task in visible
    ]
    return sorted(
        enriched,
        key=lambda task: (
            task.status != TaskStatus.CLAIMED,
            not task.game_master_recommended,
            -task.base_points,
            task.id,
        ),
    )


def task_conflict(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.post("/game/tasks/{task_id}/claim", response_model=TaskInstance)
def claim_game_task(
    task_id: str,
    context: GameContext = Depends(require_game_context),
) -> TaskInstance:
    if context.game_day.status != GameDayStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Game day is not active")
    task = require_staff_task(context, task_id)
    now = datetime.now(UTC)
    if not staff_can_take_task(context, task):
        raise HTTPException(status_code=403, detail="This task is not authorized for this staff profile")
    if not task_is_inside_window(context, task, now):
        raise HTTPException(status_code=409, detail="This task is outside its availability window")
    if task.equipment_id:
        equipment = next(
            item for item in context.project.store.equipment if item.id == task.equipment_id
        )
        if (
            equipment.customer_facing
            and local_minute(now, context.game_day.timezone)
            < context.project.store.closing_minute
        ):
            raise HTTPException(
                status_code=409,
                detail="Customer-facing equipment remains protected before store close",
            )
    active_claims = sum(
        1
        for item in context.repo.list_task_instances(context.game_day.id)
        if item.status == TaskStatus.CLAIMED
        and item.claimed_by_staff_id == context.staff.id
    )
    if active_claims >= 2:
        raise HTTPException(status_code=409, detail="Complete or release a claimed task first")
    try:
        return context.repo.claim_task_instance(
            context.game_day.id,
            task.id,
            context.staff.id,
            claimed_at=now,
            reservation_expires_at=now + timedelta(minutes=15),
        )
    except ValueError as exc:
        raise task_conflict(exc) from exc


@router.post("/game/tasks/{task_id}/release", response_model=TaskInstance)
def release_game_task(
    task_id: str,
    context: GameContext = Depends(require_game_context),
) -> TaskInstance:
    try:
        return context.repo.release_task_instance(
            context.game_day.id,
            task_id,
            context.staff.id,
            released_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise task_conflict(exc) from exc


@router.post("/game/tasks/{task_id}/complete", response_model=TaskInstance)
def complete_game_task(
    task_id: str,
    context: GameContext = Depends(require_game_context),
) -> TaskInstance:
    task = require_staff_task(context, task_id)
    now = datetime.now(UTC)
    score = score_completed_task(
        task,
        completed_at=now,
        timezone=context.game_day.timezone,
    )
    try:
        return context.repo.complete_task_instance(
            context.game_day.id,
            task.id,
            context.staff.id,
            completed_at=now,
            points=score.points,
            score_reason=score.reason,
            scoring_version=SCORING_VERSION,
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise task_conflict(ValueError(str(exc))) from exc


def build_leaderboard(
    repo: SQLiteRepository,
    game_day: GameDay,
) -> list[LeaderboardEntry]:
    staff_by_id = {
        item.id: item for item in repo.list_staff_profiles(game_day.project_id)
    }
    totals: dict[str, dict[str, int]] = {}
    for score in repo.list_score_entries(game_day.id):
        current = totals.setdefault(score.staff_id, {"points": 0, "tasks": 0})
        current["points"] += score.points
        current["tasks"] += 1
    ordered = sorted(
        totals.items(),
        key=lambda item: (
            -item[1]["points"],
            -item[1]["tasks"],
            staff_by_id[item[0]].normalized_name,
        ),
    )
    return [
        LeaderboardEntry(
            rank=index + 1,
            staff_id=staff_id,
            display_name=staff_by_id[staff_id].display_name,
            avatar_id=staff_by_id[staff_id].avatar_id,
            points=values["points"],
            tasks_completed=values["tasks"],
        )
        for index, (staff_id, values) in enumerate(ordered)
    ]


@router.get("/game/leaderboard", response_model=list[LeaderboardEntry])
def staff_leaderboard(
    context: GameContext = Depends(require_game_context),
) -> list[LeaderboardEntry]:
    return build_leaderboard(context.repo, context.game_day)


@router.get(
    "/projects/{project_id}/game-days/{game_day_id}/leaderboard",
    response_model=list[LeaderboardEntry],
)
def manager_leaderboard(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[LeaderboardEntry]:
    require_project(repo, project_id)
    return build_leaderboard(repo, require_game_day(repo, project_id, game_day_id))


@router.get(
    "/projects/{project_id}/game-days/{game_day_id}/events",
    response_model=list[GameDayEvent],
)
def game_day_events(
    project_id: str,
    game_day_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[GameDayEvent]:
    require_project(repo, project_id)
    require_game_day(repo, project_id, game_day_id)
    return repo.list_game_day_events(game_day_id)
