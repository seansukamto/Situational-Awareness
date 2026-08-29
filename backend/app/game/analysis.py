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
    GameDayLearningEvidence,
    GameDayLearningMetrics,
    GameEventType,
    GameLearningNarrative,
    ImpactEvidenceLevel,
    LearnedGamePolicy,
    StaffProfile,
    SustainabilityDomain,
    TaskInstance,
    TaskLearningAssessment,
    TaskLearningEvidence,
    TaskStatus,
)


LEARNING_INSTRUCTIONS = """Analyze one retail staff sustainability game day.
Return only the requested structured JSON and assess every supplied task exactly once.

For each task, explain its credible sustainability mechanism using only supplied evidence, preserve
the server-provided evidence classification, distinguish engagement from environmental impact,
identify missing measurement or verification, and recommend clearer task wording plus one practical
metric. Never interpret missing impact data as zero environmental benefit and never invent savings,
emissions, waste, or resource reductions. Recommendations are advisory and require manager approval.

Do not modify safety boundaries, target or rank protected personal characteristics, provide hidden
reasoning, or treat individual scores as employee performance ratings. The server independently
validates evidence labels and every learned policy change."""

POLICY_GUARDRAILS = [
    "Never create tasks for protected equipment or outside configured staff authority.",
    "Treat individual points as voluntary engagement signals, not employment performance ratings.",
    "Only measured ledger events may be presented as observed staff behaviour.",
    "Keep learned point changes between 0.90x and 1.10x of the configured template score.",
    "Task wording and measurement recommendations remain advisory until a manager approves them.",
]


SUGGESTED_METRICS = {
    SustainabilityDomain.ENERGY: "kWh avoided",
    SustainabilityDomain.WATER: "litres of water saved",
    SustainabilityDomain.WASTE: "kg diverted from general waste",
    SustainabilityDomain.FOOD: "kg of food waste avoided",
    SustainabilityDomain.TRANSPORT: "kg CO2e avoided",
    SustainabilityDomain.BUYING: "items shifted to reusable or lower-impact purchasing",
}


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


def build_learning_evidence(
    metrics: GameDayLearningMetrics,
    tasks: list[TaskInstance],
    events: list[GameDayEvent],
) -> GameDayLearningEvidence:
    releases_back = {
        task.id: sum(
            event.type == GameEventType.TASK_RELEASED_BY_STAFF
            and event.task_instance_id == task.id
            for event in events
        )
        for task in tasks
    }
    exceptions = {
        task.id: sum(
            event.type == GameEventType.TASK_EXCEPTION_REPORTED
            and event.task_instance_id == task.id
            for event in events
        )
        for task in tasks
    }
    task_evidence: list[TaskLearningEvidence] = []
    for task in tasks:
        duration = None
        if task.claimed_at and task.completed_at:
            duration = max(
                0,
                round((task.completed_at - task.claimed_at).total_seconds() / 60, 2),
            )
        evidence_level = (
            ImpactEvidenceLevel.ESTIMATED
            if task.estimated_impact_value is not None and task.estimated_impact_unit
            else ImpactEvidenceLevel.UNMEASURED
        )
        task_evidence.append(
            TaskLearningEvidence(
                task_instance_id=task.id,
                task_label=task.label,
                task_description=task.description,
                sustainability_mechanism=task.sustainability_mechanism,
                domain=task.domain,
                verification_method=task.verification_method,
                verification_status=task.verification_status,
                status=task.status,
                claimed=task.claimed_at is not None,
                releases_back=releases_back[task.id],
                exceptions_reported=exceptions[task.id],
                claim_to_completion_minutes=duration,
                points_awarded=task.points_awarded,
                impact_metric=task.impact_metric,
                estimated_impact_value=task.estimated_impact_value,
                estimated_impact_unit=task.estimated_impact_unit,
                evidence_level=evidence_level,
            )
        )
    return GameDayLearningEvidence(metrics=metrics, tasks=task_evidence)


def deterministic_task_assessment(task: TaskLearningEvidence) -> TaskLearningAssessment:
    sustainability_relevance = task.sustainability_mechanism.strip() or (
        f"This task is tagged as {task.domain}, but its sustainability mechanism was not configured."
    )
    if task.status == TaskStatus.COMPLETED:
        engagement_result = (
            f"The task was claimed and completed for {task.points_awarded} engagement points"
            f" with {task.releases_back} releases back to the pool."
        )
    elif task.claimed:
        engagement_result = "The task was claimed but not completed."
    else:
        engagement_result = "The task was released but not claimed."
    if task.evidence_level == ImpactEvidenceLevel.ESTIMATED:
        measurement_gap = (
            f"Impact is estimated as {task.estimated_impact_value} {task.estimated_impact_unit}; "
            "no measured outcome was recorded."
        )
    else:
        measurement_gap = "No environmental outcome value and unit were recorded for this task."
    metric = task.impact_metric or SUGGESTED_METRICS[task.domain]
    revision_parts = []
    if not task.sustainability_mechanism.strip():
        revision_parts.append("state how the action reduces resource use or waste")
    if not task.impact_metric:
        revision_parts.append(f"record {metric}")
    if not revision_parts:
        revision_parts.append("retain the mechanism and require the configured metric at completion")
    return TaskLearningAssessment(
        task_instance_id=task.task_instance_id,
        task_label=task.task_label,
        sustainability_relevance=sustainability_relevance,
        evidence_level=task.evidence_level,
        engagement_result=engagement_result,
        measurement_gap=measurement_gap,
        recommended_revision=(
            f"Revise the staff instruction to {', and '.join(revision_parts)}. "
            "A manager must approve the revised template."
        ),
        suggested_metric=metric,
        manager_approval_required=True,
    )


def deterministic_narrative(evidence: GameDayLearningEvidence) -> GameLearningNarrative:
    metrics = evidence.metrics
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
        task_assessments=[
            deterministic_task_assessment(task) for task in evidence.tasks
        ],
    )


def _provider_narrative(
    project: Project,
    evidence: GameDayLearningEvidence,
) -> tuple[GameLearningNarrative, str, str, bool]:
    mode = project.agent_settings.mode
    fallback = deterministic_narrative(evidence)
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
                input=evidence.model_dump_json(),
                text={"format": {
                    "type": "json_schema",
                    "name": "staff_game_learning_narrative",
                    "strict": True,
                    "schema": openai_strict_json_schema(GameLearningNarrative),
                }},
                max_output_tokens=1_500,
                store=False,
            )
            narrative = GameLearningNarrative.model_validate_json(response.output_text)
            return validate_provider_narrative(narrative, evidence), "openai", model, False
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
                    {"role": "user", "content": evidence.model_dump_json()},
                ],
                "options": {"temperature": 0.2},
            },
        )
        response.raise_for_status()
        narrative = GameLearningNarrative.model_validate_json(response.json()["message"]["content"])
        return validate_provider_narrative(narrative, evidence), "ollama", model, False
    except Exception:
        provider = "openai" if mode == AgentMode.OPENAI else "ollama"
        model = project.agent_settings.model or os.getenv(f"{provider.upper()}_MODEL", "") or "not-configured"
        return fallback, provider, model, True


def validate_provider_narrative(
    narrative: GameLearningNarrative,
    evidence: GameDayLearningEvidence,
) -> GameLearningNarrative:
    assessments_by_id = {
        assessment.task_instance_id: assessment
        for assessment in narrative.task_assessments
    }
    expected_ids = {task.task_instance_id for task in evidence.tasks}
    if len(assessments_by_id) != len(narrative.task_assessments):
        raise ValueError("Provider returned duplicate task assessments")
    if set(assessments_by_id) != expected_ids:
        raise ValueError("Provider must assess every supplied task exactly once")
    normalized = []
    for task in evidence.tasks:
        assessment = assessments_by_id[task.task_instance_id]
        normalized.append(
            assessment.model_copy(
                update={
                    "task_label": task.task_label,
                    "evidence_level": task.evidence_level,
                    "manager_approval_required": True,
                }
            )
        )
    return narrative.model_copy(update={"task_assessments": normalized})


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
        (
            "Previous tasks without configured impact evidence: "
            f"{sum(task.estimated_impact_value is None or not task.estimated_impact_unit for task in tasks)}/{len(tasks)}."
        ),
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
    evidence = build_learning_evidence(metrics, tasks, events)
    narrative, provider, model, fallback_used = _provider_narrative(project, evidence)
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
