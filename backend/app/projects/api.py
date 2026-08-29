from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from ..simulation import build_demo_store
from .bills import parse_bill_bytes
from .impact import analyse_project
from .models import (
    AnalysisRequest,
    BillConfirmation,
    BillStatus,
    EvidenceField,
    EvidenceKind,
    ImpactAnalysis,
    Project,
    ProjectCreate,
    ScenarioSettings,
    UtilityBill,
    UtilityBillDraft,
)
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
    bills = repo.list_bills(project.id)
    bill = next((item for item in bills if item.id == DEMO_BILL_ID), None)
    if bill is None:
        bill = repo.save_bill(
            project.id,
            synthetic_bill(),
            status=BillStatus.CONFIRMED,
            bill_id=DEMO_BILL_ID,
        )
    return {"project": project, "bills": [bill]}


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
        draft = parse_bill_bytes(bill_file.filename or "utility_bill", content)
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
