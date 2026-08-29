from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..agents.models import AgentIntelligenceSettings
from ..simulation.models import Store
from .models import (
    BillConfirmation,
    BillStatus,
    ChecklistSession,
    ImpactAnalysis,
    PersistedSimulationRun,
    Project,
    ProjectCreate,
    ScenarioSettings,
    UtilityBill,
    UtilityBillDraft,
)


def _now() -> datetime:
    return datetime.now(UTC)


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    store_json TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    agent_settings_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS utility_bills (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checklist_sessions (
                    id TEXT PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL,
                    configuration_hash TEXT NOT NULL,
                    game_master_rules_version TEXT NOT NULL,
                    failure_message TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_simulation_runs_project_created
                ON simulation_runs(project_id, created_at DESC);
                """
            )
            project_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "agent_settings_json" not in project_columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN agent_settings_json TEXT NOT NULL DEFAULT '{}'"
                )

    def create_project(self, payload: ProjectCreate, *, project_id: str | None = None) -> Project:
        now = _now()
        project = Project(
            id=project_id or f"project_{uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, store_json, settings_json, agent_settings_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.store.model_dump_json(),
                    project.settings.model_dump_json(),
                    project.agent_settings.model_dump_json(),
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return None if row is None else self._project_from_row(row)

    def list_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def update_settings(self, project_id: str, settings: ScenarioSettings) -> Project | None:
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET settings_json = ?, updated_at = ? WHERE id = ?",
                (settings.model_dump_json(), now.isoformat(), project_id),
            )
        return None if cursor.rowcount == 0 else self.get_project(project_id)

    def update_agent_settings(
        self,
        project_id: str,
        settings: AgentIntelligenceSettings,
    ) -> Project | None:
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET agent_settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (settings.model_dump_json(), now.isoformat(), project_id),
            )
        return None if cursor.rowcount == 0 else self.get_project(project_id)

    def update_store(self, project_id: str, store: Store) -> Project | None:
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET store_json = ?, updated_at = ? WHERE id = ?",
                (store.model_dump_json(), now.isoformat(), project_id),
            )
        return None if cursor.rowcount == 0 else self.get_project(project_id)

    def save_bill(
        self,
        project_id: str,
        draft: UtilityBillDraft,
        *,
        status: BillStatus = BillStatus.NEEDS_CONFIRMATION,
        bill_id: str | None = None,
    ) -> UtilityBill:
        bill = UtilityBill(
            id=bill_id or f"bill_{uuid4().hex[:12]}",
            project_id=project_id,
            status=status,
            average_tariff_sgd_per_kwh=round(draft.total_cost_sgd / draft.total_kwh, 6),
            created_at=_now(),
            confirmed_at=_now() if status == BillStatus.CONFIRMED else None,
            **draft.model_dump(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO utility_bills VALUES (?, ?, ?, ?, ?, ?)",
                (
                    bill.id,
                    project_id,
                    bill.model_dump_json(),
                    bill.status,
                    bill.created_at.isoformat(),
                    bill.confirmed_at.isoformat() if bill.confirmed_at else None,
                ),
            )
        return bill

    def get_bill(self, bill_id: str) -> UtilityBill | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM utility_bills WHERE id = ?", (bill_id,)
            ).fetchone()
        return None if row is None else UtilityBill.model_validate_json(row["payload_json"])

    def list_bills(self, project_id: str) -> list[UtilityBill]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM utility_bills WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [UtilityBill.model_validate_json(row["payload_json"]) for row in rows]

    def latest_confirmed_bill(self, project_id: str) -> UtilityBill | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM utility_bills
                WHERE project_id = ? AND status = ?
                ORDER BY confirmed_at DESC LIMIT 1
                """,
                (project_id, BillStatus.CONFIRMED),
            ).fetchone()
        return None if row is None else UtilityBill.model_validate_json(row["payload_json"])

    def confirm_bill(self, bill_id: str, values: BillConfirmation) -> UtilityBill | None:
        current = self.get_bill(bill_id)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                **values.model_dump(),
                "status": BillStatus.CONFIRMED,
                "average_tariff_sgd_per_kwh": round(
                    values.total_cost_sgd / values.total_kwh, 6
                ),
                "confirmed_at": _now(),
            }
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE utility_bills
                SET payload_json = ?, status = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (
                    updated.model_dump_json(),
                    updated.status,
                    updated.confirmed_at.isoformat(),
                    bill_id,
                ),
            )
        return updated

    def save_analysis(self, analysis: ImpactAnalysis) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analyses VALUES (?, ?, ?, ?)",
                (
                    analysis.id,
                    analysis.project_id,
                    analysis.model_dump_json(),
                    analysis.generated_at.isoformat(),
                ),
            )

    def get_analysis(self, analysis_id: str) -> ImpactAnalysis | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return None if row is None else ImpactAnalysis.model_validate_json(row["payload_json"])

    def create_simulation_run(self, run: PersistedSimulationRun) -> PersistedSimulationRun:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO simulation_runs (
                    id, project_id, created_at, completed_at, status, seed, sample_count,
                    configuration_hash, game_master_rules_version, failure_message, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.project_id,
                    run.created_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.status,
                    run.seed,
                    run.sample_count,
                    run.configuration_hash,
                    run.game_master_rules_version,
                    run.failure_message,
                    run.model_dump_json(),
                ),
            )
        return run

    def update_simulation_run(self, run: PersistedSimulationRun) -> PersistedSimulationRun:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE simulation_runs
                SET completed_at = ?, status = ?, failure_message = ?, payload_json = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.status,
                    run.failure_message,
                    run.model_dump_json(),
                    run.id,
                    run.project_id,
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError("Simulation run not found")
        return run

    def get_simulation_run(
        self,
        project_id: str,
        run_id: str,
    ) -> PersistedSimulationRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM simulation_runs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, run_id),
            ).fetchone()
        return None if row is None else PersistedSimulationRun.model_validate_json(row["payload_json"])

    def list_simulation_runs(self, project_id: str) -> list[PersistedSimulationRun]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM simulation_runs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [PersistedSimulationRun.model_validate_json(row["payload_json"]) for row in rows]

    def save_checklist(self, checklist: ChecklistSession) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO checklist_sessions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    checklist.id,
                    checklist.token,
                    checklist.project_id,
                    checklist.model_dump_json(),
                    checklist.expires_at.isoformat(),
                    checklist.created_at.isoformat(),
                ),
            )

    def get_checklist(self, token: str) -> ChecklistSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM checklist_sessions WHERE token = ?", (token,)
            ).fetchone()
        return None if row is None else ChecklistSession.model_validate_json(row["payload_json"])

    def update_checklist(self, checklist: ChecklistSession) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE checklist_sessions SET payload_json = ?, updated_at = ? WHERE id = ?",
                (checklist.model_dump_json(), _now().isoformat(), checklist.id),
            )

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> Project:
        payload = {
            "id": row["id"],
            "name": row["name"],
            "store": json.loads(row["store_json"]),
            "settings": json.loads(row["settings_json"]),
            "agent_settings": json.loads(row["agent_settings_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        return Project.model_validate(payload)
