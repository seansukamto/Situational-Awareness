from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from ..agents import (
    AGENT_PROMPT_TEMPLATE_VERSION,
    AgentIntelligenceSettings,
    AgentProviderLimits,
    BudgetedAgentProvider,
    build_agent_provider,
)
from ..simulation import (
    GAME_MASTER_RULES,
    GAME_MASTER_RULES_VERSION,
    GameMaster,
    build_demo_store,
    get_scenario,
)
from ..simulation.explain import explain_event
from .bills import parse_bill_bytes
from .checklists import complete_task, create_checklist
from .impact import analyse_project
from .models import (
    AnalysisRequest,
    BillConfirmation,
    BillStatus,
    ChecklistSession,
    EvidenceField,
    EvidenceKind,
    ImpactAnalysis,
    PersistedSimulationRun,
    Project,
    ProjectCreate,
    RunStatus,
    ScenarioSettings,
    SimulationRunCreate,
    SimulationRunSummary,
    StoreSettings,
    UtilityBill,
    UtilityBillDraft,
)
from .reports import build_decision_brief
from .repository import SQLiteRepository


router = APIRouter(prefix="/api", tags=["projects"])
DEMO_PROJECT_ID = "project_demo_sg_01"
DEMO_BILL_ID = "bill_demo_sg_2026_07"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def repository(request: Request) -> SQLiteRepository:
    return request.app.state.repository


def require_project(repo: SQLiteRepository, project_id: str) -> Project:
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def run_configuration_hash(project: Project, bill: UtilityBill | None) -> str:
    snapshot = {
        "store": project.store.model_dump(mode="json"),
        "scenario_settings": project.settings.model_dump(mode="json"),
        "evidence": bill.model_dump(mode="json") if bill else None,
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def with_configuration_status(
    run: PersistedSimulationRun,
    current_hash: str,
) -> PersistedSimulationRun:
    return run.model_copy(
        update={"configuration_current": run.configuration_hash == current_hash}
    )


def run_summary(run: PersistedSimulationRun) -> SimulationRunSummary:
    savings = None
    if run.impact_analysis:
        metric = run.impact_analysis.metrics.get("annual_utility_savings")
        savings = metric.p50 if metric else None
    return SimulationRunSummary(
        id=run.id,
        project_id=run.project_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
        status=run.status,
        seed=run.seed,
        sample_count=run.sample_count,
        estimated_savings_sgd=savings,
        configuration_current=run.configuration_current,
        game_master_rules_version=run.game_master_rules_version,
        agent_mode=run.agent_mode,
        agent_provider=run.agent_provider,
        agent_model=run.agent_model,
        fallback_decisions=run.agent_usage.fallback_decisions,
        provider_calls=run.agent_usage.provider_calls,
        total_tokens=run.agent_usage.total_tokens,
        estimated_cost_usd=run.agent_usage.estimated_cost_usd,
        failure_message=run.failure_message,
    )


def effective_agent_settings(
    project: Project,
    request: SimulationRunCreate,
) -> AgentIntelligenceSettings:
    overrides = request.model_dump(
        exclude_none=True,
        include={
            "mode",
            "model",
            "max_calls",
            "max_calls_per_agent",
            "timeout_seconds",
            "max_concurrency",
            "token_budget",
            "cost_budget_usd",
        },
    )
    return project.agent_settings.model_copy(update=overrides)


def scenario_provider_limits(
    settings: AgentIntelligenceSettings,
    *,
    intervention: bool,
) -> AgentProviderLimits:
    def share_integer(total: int) -> int:
        first = total // 2
        return total - first if intervention else first

    def share_float(total: float) -> float:
        first = total / 2
        return total - first if intervention else first

    return AgentProviderLimits(
        max_calls=share_integer(settings.max_calls),
        max_calls_per_agent=share_integer(settings.max_calls_per_agent),
        timeout_seconds=settings.timeout_seconds,
        max_concurrency=settings.max_concurrency,
        token_budget=share_integer(settings.token_budget),
        cost_budget_usd=share_float(settings.cost_budget_usd),
    )


def synthetic_bill() -> UtilityBillDraft:
    return UtilityBillDraft(
        filename="synthetic_sp_group_bill_2026_07.json",
        period_start="2026-07-01",
        period_end="2026-07-31",
        total_kwh=4860,
        total_cost_sgd=1550.83,
        account_label="Synthetic Orchard Road retail store",
        evidence=[
            EvidenceField(
                field="total_kwh",
                value=4860,
                unit="kWh",
                kind=EvidenceKind.MEASURED,
                source="Synthetic demo utility bill",
                confidence=1,
            ),
            EvidenceField(
                field="total_cost_sgd",
                value=1550.83,
                unit="SGD",
                kind=EvidenceKind.MEASURED,
                source="Synthetic demo utility bill",
                confidence=1,
            ),
        ],
    )


@router.post("/demo/bootstrap")
def bootstrap_demo(repo: SQLiteRepository = Depends(repository)) -> dict:
    project = repo.get_project(DEMO_PROJECT_ID)
    if project is None:
        project = repo.create_project(
            ProjectCreate(
                name="Orchard Flagship — Demo",
                store=build_demo_store(),
                settings=ScenarioSettings(),
            ),
            project_id=DEMO_PROJECT_ID,
        )
    elif len(project.store.customers) != len(build_demo_store().customers):
        project = repo.update_store(project.id, build_demo_store())
        assert project is not None
    bills = repo.list_bills(project.id)
    bill = next((item for item in bills if item.id == DEMO_BILL_ID), None)
    if bill is None:
        bill = repo.save_bill(
            project.id,
            synthetic_bill(),
            status=BillStatus.CONFIRMED,
            bill_id=DEMO_BILL_ID,
        )
    return {"project": project, "bills": repo.list_bills(project.id)}


@router.post("/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    repo: SQLiteRepository = Depends(repository),
) -> Project:
    return repo.create_project(payload)


@router.get("/projects", response_model=list[Project])
def list_projects(repo: SQLiteRepository = Depends(repository)) -> list[Project]:
    return repo.list_projects()


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str, repo: SQLiteRepository = Depends(repository)) -> Project:
    return require_project(repo, project_id)


@router.put("/projects/{project_id}/settings", response_model=Project)
def update_settings(
    project_id: str,
    settings: ScenarioSettings,
    repo: SQLiteRepository = Depends(repository),
) -> Project:
    require_project(repo, project_id)
    project = repo.update_settings(project_id, settings)
    assert project is not None
    return project


@router.put("/projects/{project_id}/agent-settings", response_model=Project)
def update_agent_settings(
    project_id: str,
    settings: AgentIntelligenceSettings,
    repo: SQLiteRepository = Depends(repository),
) -> Project:
    require_project(repo, project_id)
    project = repo.update_agent_settings(project_id, settings)
    assert project is not None
    return project


@router.put("/projects/{project_id}/store", response_model=Project)
def update_store_settings(
    project_id: str,
    settings: StoreSettings,
    repo: SQLiteRepository = Depends(repository),
) -> Project:
    current = require_project(repo, project_id)
    store = current.store.model_copy(update=settings.model_dump())
    project = repo.update_store(project_id, store)
    assert project is not None
    return project


@router.post(
    "/projects/{project_id}/runs",
    response_model=PersistedSimulationRun,
    status_code=status.HTTP_201_CREATED,
)
def create_simulation_run(
    project_id: str,
    request: SimulationRunCreate,
    repo: SQLiteRepository = Depends(repository),
) -> PersistedSimulationRun:
    project = require_project(repo, project_id)
    evidence = repo.latest_confirmed_bill(project_id)
    configuration_hash = run_configuration_hash(project, evidence)
    agent_settings = effective_agent_settings(project, request)
    provider = build_agent_provider(
        agent_settings.mode,
        model=agent_settings.model,
        timeout_seconds=agent_settings.timeout_seconds,
    )
    run = PersistedSimulationRun(
        id=f"run_{uuid4().hex[:12]}",
        project_id=project_id,
        created_at=datetime.now(UTC),
        status=RunStatus.QUEUED,
        seed=request.seed,
        sample_count=request.sample_count,
        store_snapshot=project.store.model_copy(deep=True),
        scenario_settings_snapshot=project.settings.model_copy(deep=True),
        evidence_snapshot=evidence.model_copy(deep=True) if evidence else None,
        configuration_hash=configuration_hash,
        game_master_rules_version=GAME_MASTER_RULES_VERSION,
        game_master_rules_snapshot=list(GAME_MASTER_RULES),
        agent_mode=agent_settings.mode,
        agent_provider=provider.name,
        agent_model=provider.model,
        provider_configuration_fingerprint=provider.configuration_fingerprint,
        prompt_template_version=AGENT_PROMPT_TEMPLATE_VERSION,
        agent_settings_snapshot=agent_settings,
    )
    repo.create_simulation_run(run)
    run = run.model_copy(update={"status": RunStatus.RUNNING})
    repo.update_simulation_run(run)

    try:
        baseline_provider = BudgetedAgentProvider(
            provider,
            scenario_provider_limits(agent_settings, intervention=False),
        )
        intervention_provider = BudgetedAgentProvider(
            provider,
            scenario_provider_limits(agent_settings, intervention=True),
        )
        baseline = GameMaster(
            run.store_snapshot,
            get_scenario("baseline"),
            run.seed,
            agent_provider=baseline_provider,
        ).run()
        intervention = GameMaster(
            run.store_snapshot,
            get_scenario(run.scenario_settings_snapshot.scenario_id),
            run.seed,
            agent_provider=intervention_provider,
        ).run()
        comparison = GameMaster.compare(baseline, intervention)
        analysis = None
        if run.evidence_snapshot:
            snapshot_project = project.model_copy(
                deep=True,
                update={
                    "store": run.store_snapshot,
                    "settings": run.scenario_settings_snapshot,
                },
            )
            analysis = analyse_project(
                snapshot_project,
                run.evidence_snapshot,
                samples=run.sample_count,
                seed=run.seed,
            )
            repo.save_analysis(analysis)
        run = run.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "completed_at": datetime.now(UTC),
                "comparison": comparison,
                "impact_analysis": analysis,
                "baseline_explanations": [explain_event(event) for event in baseline.events],
                "intervention_explanations": [
                    explain_event(event) for event in intervention.events
                ],
                "agent_usage": baseline.provider_usage.plus(
                    intervention.provider_usage
                ),
            }
        )
    except Exception:  # Persist an auditable state without exposing transport details.
        run = run.model_copy(
            update={
                "status": RunStatus.FAILED,
                "completed_at": datetime.now(UTC),
                "failure_message": "Simulation generation failed safely; no historical inputs were modified.",
            }
        )
    repo.update_simulation_run(run)
    return run


@router.get(
    "/projects/{project_id}/runs",
    response_model=list[SimulationRunSummary],
)
def list_simulation_runs(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[SimulationRunSummary]:
    project = require_project(repo, project_id)
    current_hash = run_configuration_hash(
        project,
        repo.latest_confirmed_bill(project_id),
    )
    return [
        run_summary(with_configuration_status(run, current_hash))
        for run in repo.list_simulation_runs(project_id)
    ]


@router.get(
    "/projects/{project_id}/runs/{run_id}",
    response_model=PersistedSimulationRun,
)
def get_simulation_run(
    project_id: str,
    run_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> PersistedSimulationRun:
    project = require_project(repo, project_id)
    run = repo.get_simulation_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    current_hash = run_configuration_hash(
        project,
        repo.latest_confirmed_bill(project_id),
    )
    return with_configuration_status(run, current_hash)


@router.get("/projects/{project_id}/bills", response_model=list[UtilityBill])
def list_bills(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> list[UtilityBill]:
    require_project(repo, project_id)
    return repo.list_bills(project_id)


@router.post(
    "/projects/{project_id}/bills/upload",
    response_model=UtilityBill,
    status_code=status.HTTP_201_CREATED,
)
async def upload_bill(
    project_id: str,
    bill_file: UploadFile = File(...),
    repo: SQLiteRepository = Depends(repository),
) -> UtilityBill:
    require_project(repo, project_id)
    content = await bill_file.read(MAX_UPLOAD_BYTES + 1)
    await bill_file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Utility bill must be 5 MB or smaller")
    if not content:
        raise HTTPException(status_code=422, detail="Utility bill is empty")
    try:
        suffix = Path(bill_file.filename or "utility_bill.txt").suffix.lower()
        safe_filename = f"uploaded_utility_bill{suffix or '.txt'}"
        draft = parse_bill_bytes(safe_filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return repo.save_bill(project_id, draft)


@router.post(
    "/projects/{project_id}/bills/synthetic",
    response_model=UtilityBill,
    status_code=status.HTTP_201_CREATED,
)
def add_synthetic_bill(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> UtilityBill:
    require_project(repo, project_id)
    return repo.save_bill(project_id, synthetic_bill())


@router.post(
    "/projects/{project_id}/bills/{bill_id}/confirm",
    response_model=UtilityBill,
)
def confirm_bill(
    project_id: str,
    bill_id: str,
    values: BillConfirmation,
    repo: SQLiteRepository = Depends(repository),
) -> UtilityBill:
    require_project(repo, project_id)
    bill = repo.get_bill(bill_id)
    if bill is None or bill.project_id != project_id:
        raise HTTPException(status_code=404, detail="Utility bill not found")
    confirmed = repo.confirm_bill(bill_id, values)
    assert confirmed is not None
    return confirmed


@router.post("/projects/{project_id}/analysis", response_model=ImpactAnalysis)
def run_impact_analysis(
    project_id: str,
    payload: AnalysisRequest,
    repo: SQLiteRepository = Depends(repository),
) -> ImpactAnalysis:
    project = require_project(repo, project_id)
    bill = repo.latest_confirmed_bill(project_id)
    if bill is None:
        raise HTTPException(
            status_code=409,
            detail="Confirm at least one utility bill before running an impact analysis",
        )
    analysis = analyse_project(
        project,
        bill,
        samples=payload.samples,
        seed=payload.seed,
    )
    repo.save_analysis(analysis)
    return analysis


@router.get("/privacy")
def privacy_summary() -> dict:
    return {
        "raw_utility_files_retained": False,
        "maximum_upload_bytes": MAX_UPLOAD_BYTES,
        "stored_data": [
            "confirmed utility fields",
            "store configuration",
            "scenario assumptions",
            "simulation outputs",
            "staff checklist completion state",
        ],
        "excluded_by_default": [
            "customer names",
            "staff names",
            "payment details",
            "raw utility files",
        ],
        "storage": "Local SQLite database configured by the operator",
    }


@router.post(
    "/projects/{project_id}/checklists",
    response_model=ChecklistSession,
    status_code=status.HTTP_201_CREATED,
)
def create_staff_checklist(
    project_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> ChecklistSession:
    project = require_project(repo, project_id)
    checklist = create_checklist(project)
    repo.save_checklist(checklist)
    return checklist


def require_checklist(repo: SQLiteRepository, token: str) -> ChecklistSession:
    checklist = repo.get_checklist(token)
    if checklist is None:
        raise HTTPException(status_code=404, detail="Checklist not found")
    if checklist.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Checklist link has expired")
    return checklist


@router.get("/checklists/{token}", response_model=ChecklistSession)
def get_staff_checklist(
    token: str,
    repo: SQLiteRepository = Depends(repository),
) -> ChecklistSession:
    return require_checklist(repo, token)


@router.post(
    "/checklists/{token}/tasks/{task_id}/complete",
    response_model=ChecklistSession,
)
def complete_staff_task(
    token: str,
    task_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> ChecklistSession:
    checklist = require_checklist(repo, token)
    try:
        updated = complete_task(checklist, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    repo.update_checklist(updated)
    return updated


@router.get(
    "/projects/{project_id}/runs/{run_id}/report.md",
    response_class=PlainTextResponse,
)
def download_run_decision_brief(
    project_id: str,
    run_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> PlainTextResponse:
    project = require_project(repo, project_id)
    run = repo.get_simulation_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    if run.impact_analysis is None or run.evidence_snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="This run has no confirmed evidence-backed impact analysis",
        )
    snapshot_project = project.model_copy(
        deep=True,
        update={
            "store": run.store_snapshot,
            "settings": run.scenario_settings_snapshot,
        },
    )
    report = build_decision_brief(
        snapshot_project,
        run.evidence_snapshot,
        run.impact_analysis,
    )
    filename = f"situational-awareness-{run.id}-decision-brief.md"
    return PlainTextResponse(
        report,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/projects/{project_id}/analyses/{analysis_id}/report.md",
    response_class=PlainTextResponse,
)
def download_decision_brief(
    project_id: str,
    analysis_id: str,
    repo: SQLiteRepository = Depends(repository),
) -> PlainTextResponse:
    project = require_project(repo, project_id)
    analysis = repo.get_analysis(analysis_id)
    if analysis is None or analysis.project_id != project_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    bill = repo.get_bill(analysis.bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Analysis bill not found")
    report = build_decision_brief(project, bill, analysis)
    filename = f"situational-awareness-{project_id}-decision-brief.md"
    return PlainTextResponse(
        report,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
