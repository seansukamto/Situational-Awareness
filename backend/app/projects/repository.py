from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..simulation.models import Store
from .models import (
    BillConfirmation,
    BillStatus,
    ImpactAnalysis,
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
                """
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
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project.id,
                    project.name,
                    project.store.model_dump_json(),
                    project.settings.model_dump_json(),
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

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> Project:
        payload = {
            "id": row["id"],
            "name": row["name"],
            "store": json.loads(row["store_json"]),
            "settings": json.loads(row["settings_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        return Project.model_validate(payload)
