import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .projects.api import router as projects_router
from .projects.repository import SQLiteRepository
from .simulation import GameMaster, build_demo_store, get_scenario
from .simulation.models import ScenarioComparison, SimulationRun, Store
from .simulation.scenarios import list_scenarios


app = FastAPI(
    title="Situational Awareness API",
    version="0.1.0",
    description="Auditable retail sustainability simulations governed by an authoritative Game Master.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
database_path = Path(
    os.getenv(
        "SA_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "situational_awareness.sqlite3"),
    )
)
app.state.repository = SQLiteRepository(database_path)
app.include_router(projects_router)


class RunRequest(BaseModel):
    scenario_id: str
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "situational-awareness-api"}


@app.get("/api/demo/store", response_model=Store)
def demo_store() -> Store:
    return build_demo_store()


@app.get("/api/scenarios")
def scenarios():
    return list_scenarios()


@app.post("/api/simulations/run", response_model=SimulationRun)
def run_simulation(request: RunRequest) -> SimulationRun:
    try:
        scenario = get_scenario(request.scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GameMaster(build_demo_store(), scenario, request.seed).run()


@app.get("/api/simulations/compare", response_model=ScenarioComparison)
def compare_simulations(seed: int = Query(default=42, ge=0, le=2_147_483_647)):
    store = build_demo_store()
    baseline = GameMaster(store, get_scenario("baseline"), seed).run()
    intervention = GameMaster(store, get_scenario("green-close"), seed).run()
    return GameMaster.compare(baseline, intervention)
