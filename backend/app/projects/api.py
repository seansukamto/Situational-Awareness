from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from ..simulation import build_demo_store
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
    Project,
    ProjectCreate,
    ScenarioSettings,
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
