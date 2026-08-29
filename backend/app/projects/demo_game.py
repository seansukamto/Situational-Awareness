from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from ..agents.models import AgentMode
from ..game.analysis import (
    build_learned_policy,
    build_learning_evidence,
    calculate_learning_metrics,
    deterministic_narrative,
)
from ..game.models import (
    GAME_LEARNING_PROMPT_VERSION,
    GameDay,
    GameDayAnalysis,
    GameDayEvent,
    GameDayStatus,
    GameEventType,
    StaffProfile,
    SustainabilityDomain,
    TaskInstance,
    TaskStatus,
    TaskTemplate,
    VerificationMethod,
    normalize_staff_name,
)
from ..game.scoring import SCORING_VERSION
from ..game.security import hash_staff_pin
from ..simulation.models import AgentRole
from .models import Project
from .repository import SQLiteRepository


DEMO_GAME_CONTENT_VERSION = 2
DEMO_JOIN_PIN = "2468"
_DEMO_SEED_LOCK = Lock()


def _local_time(project: Project, local_date, minute: int) -> datetime:
    local_midnight = datetime.combine(
        local_date,
        time.min,
        tzinfo=ZoneInfo(project.store.timezone),
    )
    return (local_midnight + timedelta(minutes=minute)).astimezone(UTC)


def _staff_profiles(project: Project, created_at: datetime) -> list[StaffProfile]:
    all_zones = [zone.id for zone in project.store.zones]
    manager_equipment = [
        item.id for item in project.store.equipment if str(item.criticality) != "protected"
    ]
    associate_equipment = [
        item.id
        for item in project.store.equipment
        if str(item.criticality) == "non_critical"
    ]
    rows = [
        (
            "staff_demo_maya",
            "Maya Lim",
            AgentRole.MANAGER,
            "shift-manager",
            all_zones,
            manager_equipment,
            8 * 60,
            18 * 60,
        ),
        (
            "staff_demo_daniel",
            "Daniel Tan",
            AgentRole.CLOSING_ASSOCIATE,
            "associate",
            ["sales_floor", "display_wall", "stockroom"],
            associate_equipment,
            9 * 60,
            22 * 60,
        ),
        (
            "staff_demo_aisha",
            "Aisha Rahman",
            AgentRole.CASHIER,
            "display-browser",
            ["checkout", "sales_floor"],
            [],
            10 * 60,
            19 * 60,
        ),
        (
            "staff_demo_lucas",
            "Lucas Wong",
            AgentRole.CLOSING_ASSOCIATE,
            "value-seeker",
            ["sales_floor", "display_wall", "stockroom"],
            associate_equipment,
            13 * 60,
            22 * 60,
        ),
    ]
    return [
        StaffProfile(
            id=staff_id,
            project_id=project.id,
            display_name=name,
            normalized_name=normalize_staff_name(name),
            role=role,
            avatar_id=avatar_id,
            authorized_zone_ids=zones,
            authorized_equipment_ids=equipment,
            default_shift_start=shift_start,
            default_shift_end=shift_end,
            created_at=created_at,
            updated_at=created_at,
        )
        for staff_id, name, role, avatar_id, zones, equipment, shift_start, shift_end in rows
    ]


def _task_templates(project: Project, created_at: datetime) -> list[TaskTemplate]:
    common_roles = [AgentRole.MANAGER, AgentRole.CLOSING_ASSOCIATE, AgentRole.CASHIER]
    rows = [
        {
            "id": "template_demo_energy",
            "label": "Opening stockroom lighting check",
            "description": "Check that only the stockroom lighting needed for active work is switched on.",
            "sustainability_mechanism": "Avoids electricity use from lighting empty stockroom areas.",
            "impact_metric": "lighting zones left off when unused",
            "domain": SustainabilityDomain.ENERGY,
            "zone_id": "stockroom",
            "equipment_id": "stockroom_lights",
            "allowed_roles": [AgentRole.MANAGER, AgentRole.CLOSING_ASSOCIATE],
            "expected_minutes": 15,
            "base_points": 55,
            "maximum_points": 65,
            "estimated_impact_value": 0.7,
        },
        {
            "id": "template_demo_water",
            "label": "Refill station leak check",
            "description": "Inspect the staff refill point and log any dripping tap or visible leak for follow-up.",
            "sustainability_mechanism": "Early leak reporting prevents avoidable potable-water loss.",
            "impact_metric": "leaks checked and reported",
            "domain": SustainabilityDomain.WATER,
            "zone_id": "sales_floor",
            "equipment_id": None,
            "allowed_roles": common_roles,
            "expected_minutes": 15,
            "base_points": 50,
            "maximum_points": 60,
            "estimated_impact_value": None,
        },
        {
            "id": "template_demo_waste",
            "label": "Recover reusable delivery packaging",
            "description": "Sort clean reusable packaging into the recovery container and record the recovered weight.",
            "sustainability_mechanism": "Diverts reusable packaging from general waste so it can replace new packaging.",
            "impact_metric": "kg diverted from general waste",
            "domain": SustainabilityDomain.WASTE,
            "zone_id": "stockroom",
            "equipment_id": None,
            "allowed_roles": common_roles,
            "expected_minutes": 25,
            "base_points": 70,
            "maximum_points": 80,
            "estimated_impact_value": 2.8,
        },
        {
            "id": "template_demo_food",
            "label": "Low-waste staff break setup",
            "description": "Set out reusable cups and label the food-scrap collection point before the team break.",
            "sustainability_mechanism": "Reduces single-use serviceware and keeps food scraps out of general waste.",
            "impact_metric": "single-use items avoided",
            "domain": SustainabilityDomain.FOOD,
            "zone_id": "stockroom",
            "equipment_id": None,
            "allowed_roles": common_roles,
            "expected_minutes": 20,
            "base_points": 45,
            "maximum_points": 55,
            "estimated_impact_value": None,
        },
        {
            "id": "template_demo_transport",
            "label": "Stage delivery totes for return",
            "description": "Stack empty supplier totes at the collection point and record the tote count for the next pickup.",
            "sustainability_mechanism": "Returns durable totes into the delivery loop instead of replacing them with disposable packaging.",
            "impact_metric": "reusable totes returned",
            "domain": SustainabilityDomain.TRANSPORT,
            "zone_id": "stockroom",
            "equipment_id": None,
            "allowed_roles": [AgentRole.MANAGER, AgentRole.CLOSING_ASSOCIATE],
            "expected_minutes": 25,
            "base_points": 65,
            "maximum_points": 75,
            "estimated_impact_value": 1.6,
        },
        {
            "id": "template_demo_buying",
            "label": "Flag low-stock reusable supplies",
            "description": "Check reusable cleaning and staff supplies, then flag only items that need replenishment.",
            "sustainability_mechanism": "Prevents unnecessary purchasing while keeping reusable alternatives available.",
            "impact_metric": "unnecessary replenishment items avoided",
            "domain": SustainabilityDomain.BUYING,
            "zone_id": "sales_floor",
            "equipment_id": None,
            "allowed_roles": common_roles,
            "expected_minutes": 20,
            "base_points": 60,
            "maximum_points": 70,
            "estimated_impact_value": 0.9,
        },
    ]
    return [
        TaskTemplate(
            id=row.pop("id"),
            project_id=project.id,
            # Demo tasks stay claimable whenever a manager opens a presentation
            # session; their replay is still paced inside the configured shift.
            available_from_minute=0,
            available_until_minute=24 * 60,
            allowed_staff_ids=[],
            verification_method=VerificationMethod.SELF_CONFIRMATION,
            estimated_impact_unit="kg CO2e" if row["estimated_impact_value"] is not None else None,
            active=True,
            created_at=created_at + timedelta(seconds=index),
            updated_at=created_at + timedelta(seconds=index),
            **row,
        )
        for index, row in enumerate(rows)
    ]


def _task_instances(
    project: Project,
    game_day: GameDay,
    templates: list[TaskTemplate],
    released_at: datetime,
) -> list[TaskInstance]:
    return [
        TaskInstance(
            id=f"task_demo_{index + 1:02d}",
            game_day_id=game_day.id,
            project_id=project.id,
            template_id=template.id,
            label=template.label,
            description=template.description,
            sustainability_mechanism=template.sustainability_mechanism,
            impact_metric=template.impact_metric,
            domain=template.domain,
            zone_id=template.zone_id,
            equipment_id=template.equipment_id,
            allowed_roles=template.allowed_roles,
            allowed_staff_ids=[],
            available_from_minute=template.available_from_minute,
            available_until_minute=template.available_until_minute,
            expected_minutes=template.expected_minutes,
            base_points=template.base_points,
            maximum_points=template.maximum_points,
            verification_method=template.verification_method,
            estimated_impact_value=template.estimated_impact_value,
            estimated_impact_unit=template.estimated_impact_unit,
            status=TaskStatus.AVAILABLE,
            scoring_version=SCORING_VERSION,
            created_at=released_at,
            updated_at=released_at,
        )
        for index, template in enumerate(templates)
    ]


def seed_demo_game_content(repo: SQLiteRepository, project: Project) -> None:
    with _DEMO_SEED_LOCK:
        if repo.get_demo_content_version(project.id) >= DEMO_GAME_CONTENT_VERSION:
            return
        _seed_demo_game_content(repo, project)


def _seed_demo_game_content(repo: SQLiteRepository, project: Project) -> None:
    repo.reset_demo_game_content(project.id)

    local_today = datetime.now(UTC).astimezone(ZoneInfo(project.store.timezone)).date()
    demo_date = local_today - timedelta(days=1)
    created_at = _local_time(project, demo_date, project.store.opening_minute - 15)
    staff = _staff_profiles(project, created_at)
    salt, pin_hash = hash_staff_pin(DEMO_JOIN_PIN)
    for profile in staff:
        repo.create_staff_profile(profile, salt, pin_hash)

    templates = _task_templates(project, created_at)
    for template in templates:
        repo.create_task_template(template)

    started_at = _local_time(project, demo_date, project.store.opening_minute)
    completed_at = _local_time(project, demo_date, project.store.closing_minute)
    game_day = GameDay(
        id="day_demo_showcase",
        project_id=project.id,
        local_date=demo_date,
        timezone=project.store.timezone,
        start_minute=project.store.opening_minute,
        end_minute=project.store.closing_minute,
        status=GameDayStatus.SCHEDULED,
        join_token="demo-showcase-completed",
        created_at=created_at,
    )
    repo.create_game_day(game_day)
    tasks = _task_instances(project, game_day, templates, started_at)
    repo.create_task_instances(tasks)

    active_day = game_day.model_copy(
        update={"status": GameDayStatus.ACTIVE, "started_at": started_at}
    )
    repo.update_game_day(active_day)
    repo.append_game_event(GameDayEvent(
        seq=0,
        game_day_id=game_day.id,
        occurred_at=started_at,
        type=GameEventType.DAY_STARTED,
        message="The staff sustainability game started.",
        source="manager",
        evidence_kind="measured",
        data={"task_count": len(tasks), "policy_version": game_day.policy_version},
    ))

    staff_by_id = {profile.id: profile for profile in staff}
    for staff_id, minute in [
        ("staff_demo_maya", 8 * 60),
        ("staff_demo_daniel", 9 * 60),
        ("staff_demo_aisha", 10 * 60),
        ("staff_demo_lucas", 13 * 60),
    ]:
        repo.append_game_event(GameDayEvent(
            seq=0,
            game_day_id=game_day.id,
            occurred_at=_local_time(project, demo_date, minute),
            type=GameEventType.STAFF_JOINED,
            message=f"{staff_by_id[staff_id].display_name} started their shift.",
            staff_id=staff_id,
            source="staff",
            evidence_kind="measured",
        ))

    completed_work = [
        (tasks[0], "staff_demo_maya", 8 * 60 + 15, 8 * 60 + 32, 55),
        (tasks[1], "staff_demo_aisha", 10 * 60 + 20, 10 * 60 + 38, 50),
        (tasks[2], "staff_demo_daniel", 11 * 60 + 45, 12 * 60 + 14, 75),
        (tasks[4], "staff_demo_lucas", 15 * 60, 15 * 60 + 28, 65),
        (tasks[5], "staff_demo_daniel", 19 * 60 + 30, 19 * 60 + 54, 60),
    ]
    for task, staff_id, claim_minute, complete_minute, points in completed_work:
        claim_time = _local_time(project, demo_date, claim_minute)
        repo.claim_task_instance(
            game_day.id,
            task.id,
            staff_id,
            claimed_at=claim_time,
            reservation_expires_at=claim_time + timedelta(minutes=45),
        )
        repo.complete_task_instance(
            game_day.id,
            task.id,
            staff_id,
            completed_at=_local_time(project, demo_date, complete_minute),
            points=points,
            score_reason=f"{points} demo engagement points",
            scoring_version=SCORING_VERSION,
        )

    completed_day = active_day.model_copy(
        update={"status": GameDayStatus.COMPLETED, "completed_at": completed_at}
    )
    repo.update_game_day(completed_day)
    repo.append_game_event(GameDayEvent(
        seq=0,
        game_day_id=game_day.id,
        occurred_at=completed_at,
        type=GameEventType.DAY_COMPLETED,
        message="The staff sustainability game day ended after the scheduled shift.",
        source="manager",
        evidence_kind="measured",
    ))

    stored_tasks = repo.list_task_instances(game_day.id)
    events = repo.list_game_day_events(game_day.id)
    metrics = calculate_learning_metrics(stored_tasks, events, staff)
    evidence = build_learning_evidence(metrics, stored_tasks, events)
    policy = build_learned_policy(
        project.id,
        completed_day,
        metrics,
        stored_tasks,
        None,
        completed_at,
    )
    analysis = GameDayAnalysis(
        id="game_analysis_demo_showcase",
        project_id=project.id,
        game_day_id=game_day.id,
        analyzer_mode=AgentMode.DETERMINISTIC,
        provider="deterministic",
        model="staff-game-learning-rules",
        fallback_used=False,
        prompt_template_version=GAME_LEARNING_PROMPT_VERSION,
        metrics=metrics,
        narrative=deterministic_narrative(evidence),
        learned_policy_version=policy.version,
        created_at=completed_at,
    )
    repo.save_game_learning(analysis, policy)
    repo.set_demo_content_version(project.id, DEMO_GAME_CONTENT_VERSION)
