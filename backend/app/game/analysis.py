from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from ..agents.models import AgentMode
from ..agents.schema import openai_strict_json_schema
from ..projects.models import Project
from .models import (
    GAME_LEARNING_PROMPT_VERSION,
    DomainPerformance,
    GameDay,
    GameDayAnalysis,
    GameDayEvent,
    GameDayLearningMetrics,
    GameLearningNarrative,
    LearnedGamePolicy,
    StaffProfile,
    SustainabilityDomain,
    TaskInstance,
    TaskStatus,
)


LEARNING_INSTRUCTIONS = """Analyze one retail staff sustainability game day.
Return only the requested structured JSON. Describe observable patterns and practical task-design
improvements. Do not invent measured impact, modify safety boundaries, target or rank protected
personal characteristics, or provide hidden reasoning. Individual scores are engagement signals,
not employee performance ratings. The server independently validates every learned policy change."""

POLICY_GUARDRAILS = [
    "Never create tasks for protected equipment or outside configured staff authority.",
    "Treat individual points as voluntary engagement signals, not employment performance ratings.",
    "Only measured ledger events may be presented as observed staff behaviour.",
    "Keep learned point changes between 0.90x and 1.10x of the configured template score.",
]


def calculate_learning_metrics(
    tasks: list[TaskInstance],
    events: list[GameDayEvent],
    staff: list[StaffProfile],
) -> GameDayLearningMetrics:
    joined_staff = {event.staff_id for event in events if event.type == "staff_joined" and event.staff_id}
    claimed_task_ids = {
        event.task_instance_id
        for event in events
        if event.type == "task_claimed" and event.task_instance_id
    }
    completed = [task for task in tasks if task.status == TaskStatus.COMPLETED]
    released_back = sum(event.type == "task_released_by_staff" for event in events)
    domain_performance: dict[SustainabilityDomain, DomainPerformance] = {}
    impact_units = {
        task.estimated_impact_unit
        for task in completed
        if task.estimated_impact_unit and task.estimated_impact_value is not None
    }
    for domain in SustainabilityDomain:
        domain_tasks = [task for task in tasks if task.domain == domain]
        if not domain_tasks:
            continue
        domain_completed = [task for task in domain_tasks if task.status == TaskStatus.COMPLETED]
        units = {
            task.estimated_impact_unit
            for task in domain_completed
            if task.estimated_impact_unit and task.estimated_impact_value is not None
        }
        impact = sum(task.estimated_impact_value or 0 for task in domain_completed)
        domain_performance[domain] = DomainPerformance(
            released=len(domain_tasks),
            claimed=sum(task.id in claimed_task_ids for task in domain_tasks),
            completed=len(domain_completed),
            completion_rate=len(domain_completed) / len(domain_tasks),
            estimated_impact=round(impact, 4),
            impact_unit=next(iter(units)) if len(units) == 1 else "mixed" if units else None,
        )
    return GameDayLearningMetrics(
        active_staff_profiles=sum(profile.active for profile in staff),
        participating_staff=len(joined_staff),
        tasks_released=len(tasks),
        tasks_claimed=len(claimed_task_ids),
        tasks_completed=len(completed),
        tasks_released_back=released_back,
        completion_rate=len(completed) / len(tasks) if tasks else 0,
        total_points=sum(task.points_awarded for task in completed),
        estimated_impact_total=round(sum(task.estimated_impact_value or 0 for task in completed), 4),
        domain_performance=domain_performance,
    )


def deterministic_narrative(metrics: GameDayLearningMetrics) -> GameLearningNarrative:
    participation = (
        metrics.participating_staff / metrics.active_staff_profiles
        if metrics.active_staff_profiles
        else 0
    )
    patterns = [
        f"{metrics.tasks_completed} of {metrics.tasks_released} released tasks were completed.",
        f"{metrics.participating_staff} of {metrics.active_staff_profiles} active staff profiles joined.",
    ]
    if metrics.tasks_released_back:
        patterns.append(f"Staff returned {metrics.tasks_released_back} claimed tasks to the pool.")
    recommendations: list[str] = []
    if participation < 0.6:
        recommendations.append("Make the join QR visible at shift check-in and explain that participation is voluntary.")
    if metrics.completion_rate < 0.5:
        recommendations.append("Release fewer, clearer challenges and boost under-completed domains within the scoring guardrail.")
    if not recommendations:
        recommendations.append("Keep the current task mix and validate the pattern over additional game days.")
    return GameLearningNarrative(
        summary=(
            f"The day recorded {metrics.participating_staff} participants, "
            f"{metrics.tasks_completed} completed sustainability tasks, and "
            f"{metrics.total_points} individual points."
        ),
        patterns=patterns,
        recommendations=recommendations,
    )


def _provider_narrative(
    project: Project,
    metrics: GameDayLearningMetrics,
) -> tuple[GameLearningNarrative, str, str, bool]:
    mode = project.agent_settings.mode
    fallback = deterministic_narrative(metrics)
    if mode == AgentMode.DETERMINISTIC:
        return fallback, "deterministic", "staff-game-learning-rules", False
    try:
        if mode == AgentMode.OPENAI:
            configured_model = os.getenv("OPENAI_MODEL", "")
            model = project.agent_settings.model or configured_model
            if not os.getenv("OPENAI_API_KEY") or not configured_model or model != configured_model:
                raise RuntimeError("OpenAI learning analysis is not configured")
            from openai import OpenAI

            client = OpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                timeout=project.agent_settings.timeout_seconds,
                max_retries=0,
            )
            response = client.responses.create(
                model=model,
                instructions=LEARNING_INSTRUCTIONS,
                input=metrics.model_dump_json(),
                text={"format": {
                    "type": "json_schema",
                    "name": "staff_game_learning_narrative",
                    "strict": True,
                    "schema": openai_strict_json_schema(GameLearningNarrative),
                }},
                max_output_tokens=500,
                store=False,
            )
            return GameLearningNarrative.model_validate_json(response.output_text), "openai", model, False
        configured_model = os.getenv("OLLAMA_MODEL", "")
        base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        model = project.agent_settings.model or configured_model
        if not base_url or not configured_model or model != configured_model:
            raise RuntimeError("Ollama learning analysis is not configured")
        response = httpx.post(
            f"{base_url}/api/chat",
            timeout=project.agent_settings.timeout_seconds,
            json={
                "model": model,
                "stream": False,
                "format": GameLearningNarrative.model_json_schema(),
                "messages": [
                    {"role": "system", "content": LEARNING_INSTRUCTIONS},
                    {"role": "user", "content": metrics.model_dump_json()},
                ],
                "options": {"temperature": 0.2},
            },
        )
        response.raise_for_status()
        narrative = GameLearningNarrative.model_validate_json(response.json()["message"]["content"])
        return narrative, "ollama", model, False
    except Exception:
        provider = "openai" if mode == AgentMode.OPENAI else "ollama"
        model = project.agent_settings.model or os.getenv(f"{provider.upper()}_MODEL", "") or "not-configured"
        return fallback, provider, model, True


def build_learned_policy(
    project_id: str,
    game_day: GameDay,
    metrics: GameDayLearningMetrics,
    tasks: list[TaskInstance],
    previous: LearnedGamePolicy | None,
    created_at: datetime,
) -> LearnedGamePolicy:
    multipliers = {domain: 1.0 for domain in SustainabilityDomain}
    if previous:
        multipliers.update(previous.domain_point_multipliers)
    for domain, performance in metrics.domain_performance.items():
        if performance.released and performance.completion_rate < 0.5:
            multipliers[domain] = min(1.1, round(multipliers[domain] + 0.05, 2))
        elif performance.released >= 3 and performance.completion_rate >= 0.9:
            multipliers[domain] = max(0.9, round(multipliers[domain] - 0.02, 2))
    staff_domain_preferences = dict(previous.staff_domain_preferences) if previous else {}
    completion_counts: dict[str, dict[SustainabilityDomain, int]] = {}
    for task in tasks:
        if task.status != TaskStatus.COMPLETED or not task.claimed_by_staff_id:
            continue
        staff_counts = completion_counts.setdefault(task.claimed_by_staff_id, {})
        staff_counts[task.domain] = staff_counts.get(task.domain, 0) + 1
    for staff_id, counts in completion_counts.items():
        staff_domain_preferences[staff_id] = [
            domain
            for domain, _ in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[:3]
        ]
    context = [
        f"Previous day participation: {metrics.participating_staff}/{metrics.active_staff_profiles} active profiles.",
        f"Previous task completion: {metrics.tasks_completed}/{metrics.tasks_released} released tasks.",
        f"Previous task releases back to pool: {metrics.tasks_released_back}.",
        f"Personalized domain history available for {len(staff_domain_preferences)} staff profiles.",
    ]
    return LearnedGamePolicy(
        version=f"staff-game-policy-{game_day.local_date.isoformat()}-{game_day.id[-6:]}",
        project_id=project_id,
        previous_version=previous.version if previous else game_day.policy_version,
        source_game_day_id=game_day.id,
        prompt_context=context,
        domain_point_multipliers=multipliers,
        staff_domain_preferences=staff_domain_preferences,
        guardrails=POLICY_GUARDRAILS,
        created_at=created_at,
    )


def analyze_game_day(
    project: Project,
    game_day: GameDay,
    tasks: list[TaskInstance],
    events: list[GameDayEvent],
    staff: list[StaffProfile],
    previous_policy: LearnedGamePolicy | None,
) -> tuple[GameDayAnalysis, LearnedGamePolicy]:
    created_at = datetime.now(UTC)
    metrics = calculate_learning_metrics(tasks, events, staff)
    narrative, provider, model, fallback_used = _provider_narrative(project, metrics)
    policy = build_learned_policy(project.id, game_day, metrics, tasks, previous_policy, created_at)
    analysis = GameDayAnalysis(
        id=f"game_analysis_{uuid4().hex[:12]}",
        project_id=project.id,
        game_day_id=game_day.id,
        analyzer_mode=project.agent_settings.mode,
        provider=provider,
        model=model,
        fallback_used=fallback_used,
        prompt_template_version=GAME_LEARNING_PROMPT_VERSION,
        metrics=metrics,
        narrative=narrative,
        learned_policy_version=policy.version,
        created_at=created_at,
    )
    return analysis, policy
