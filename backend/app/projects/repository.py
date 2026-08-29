from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..agents.models import AgentIntelligenceSettings
from ..game.models import (
    GameDay,
    GameDayEvent,
    GameEventType,
    GameStaffSession,
    ScoreEntry,
    StaffProfile,
    TaskInstance,
    TaskStatus,
    TaskTemplate,
    VerificationStatus,
)
from ..game.security import verify_staff_pin
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
                CREATE TABLE IF NOT EXISTS schema_versions (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
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
            self._migrate_live_game_staff(connection)
            self._migrate_live_game_days(connection)

    @staticmethod
    def _migrate_live_game_staff(connection: sqlite3.Connection) -> None:
        version = 1
        applied = connection.execute(
            "SELECT 1 FROM schema_versions WHERE version = ?", (version,)
        ).fetchone()
        if applied:
            return
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS staff_profiles (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                normalized_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                pin_salt BLOB NOT NULL,
                pin_hash BLOB NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, normalized_name)
            );
            CREATE INDEX IF NOT EXISTS idx_staff_profiles_project_active
            ON staff_profiles(project_id, active, normalized_name);
            """
        )
        connection.execute(
            "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
            (version, _now().isoformat()),
        )

    @staticmethod
    def _migrate_live_game_days(connection: sqlite3.Connection) -> None:
        version = 2
        applied = connection.execute(
            "SELECT 1 FROM schema_versions WHERE version = ?", (version,)
        ).fetchone()
        if applied:
            return
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_templates (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                active INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_templates_project_active
            ON task_templates(project_id, active, created_at);

            CREATE TABLE IF NOT EXISTS game_days (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                local_date TEXT NOT NULL,
                status TEXT NOT NULL,
                join_token TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, local_date)
            );
            CREATE INDEX IF NOT EXISTS idx_game_days_project_date
            ON game_days(project_id, local_date DESC);

            CREATE TABLE IF NOT EXISTS game_staff_sessions (
                id TEXT PRIMARY KEY,
                game_day_id TEXT NOT NULL REFERENCES game_days(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                staff_id TEXT NOT NULL REFERENCES staff_profiles(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_game_sessions_day_staff
            ON game_staff_sessions(game_day_id, staff_id);

            CREATE TABLE IF NOT EXISTS task_instances (
                id TEXT PRIMARY KEY,
                game_day_id TEXT NOT NULL REFERENCES game_days(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                template_id TEXT NOT NULL REFERENCES task_templates(id),
                status TEXT NOT NULL,
                claimed_by_staff_id TEXT REFERENCES staff_profiles(id),
                reservation_expires_at TEXT,
                version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(game_day_id, template_id)
            );
            CREATE INDEX IF NOT EXISTS idx_task_instances_day_status
            ON task_instances(game_day_id, status, created_at);

            CREATE TABLE IF NOT EXISTS game_day_events (
                game_day_id TEXT NOT NULL REFERENCES game_days(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                staff_id TEXT REFERENCES staff_profiles(id),
                task_instance_id TEXT REFERENCES task_instances(id),
                payload_json TEXT NOT NULL,
                PRIMARY KEY(game_day_id, seq)
            );

            CREATE TABLE IF NOT EXISTS score_entries (
                id TEXT PRIMARY KEY,
                game_day_id TEXT NOT NULL REFERENCES game_days(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                staff_id TEXT NOT NULL REFERENCES staff_profiles(id),
                task_instance_id TEXT NOT NULL REFERENCES task_instances(id),
                points INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(game_day_id, task_instance_id)
            );
            CREATE INDEX IF NOT EXISTS idx_score_entries_day_staff
            ON score_entries(game_day_id, staff_id);
            """
        )
        connection.execute(
            "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
            (version, _now().isoformat()),
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

    def create_staff_profile(
        self,
        profile: StaffProfile,
        pin_salt: bytes,
        pin_hash: bytes,
    ) -> StaffProfile:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO staff_profiles (
                    id, project_id, normalized_name, payload_json, pin_salt,
                    pin_hash, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.project_id,
                    profile.normalized_name,
                    profile.model_dump_json(),
                    pin_salt,
                    pin_hash,
                    int(profile.active),
                    profile.created_at.isoformat(),
                    profile.updated_at.isoformat(),
                ),
            )
        return profile

    def get_staff_profile(
        self,
        project_id: str,
        staff_id: str,
    ) -> StaffProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM staff_profiles
                WHERE project_id = ? AND id = ?
                """,
                (project_id, staff_id),
            ).fetchone()
        return None if row is None else StaffProfile.model_validate_json(row["payload_json"])

    def list_staff_profiles(self, project_id: str) -> list[StaffProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM staff_profiles
                WHERE project_id = ?
                ORDER BY active DESC, normalized_name ASC
                """,
                (project_id,),
            ).fetchall()
        return [StaffProfile.model_validate_json(row["payload_json"]) for row in rows]

    def update_staff_profile(self, profile: StaffProfile) -> StaffProfile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE staff_profiles
                SET normalized_name = ?, payload_json = ?, active = ?, updated_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (
                    profile.normalized_name,
                    profile.model_dump_json(),
                    int(profile.active),
                    profile.updated_at.isoformat(),
                    profile.project_id,
                    profile.id,
                ),
            )
        return None if cursor.rowcount == 0 else profile

    def update_staff_pin(
        self,
        project_id: str,
        staff_id: str,
        pin_salt: bytes,
        pin_hash: bytes,
    ) -> StaffProfile | None:
        current = self.get_staff_profile(project_id, staff_id)
        if current is None:
            return None
        updated = current.model_copy(update={"updated_at": _now()})
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE staff_profiles
                SET pin_salt = ?, pin_hash = ?, payload_json = ?, updated_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (
                    pin_salt,
                    pin_hash,
                    updated.model_dump_json(),
                    updated.updated_at.isoformat(),
                    project_id,
                    staff_id,
                ),
            )
        return None if cursor.rowcount == 0 else updated

    def verify_staff_pin(
        self,
        project_id: str,
        staff_id: str,
        pin: str,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT pin_salt, pin_hash FROM staff_profiles
                WHERE project_id = ? AND id = ? AND active = 1
                """,
                (project_id, staff_id),
            ).fetchone()
        if row is None:
            return False
        return verify_staff_pin(pin, row["pin_salt"], row["pin_hash"])

    def create_task_template(self, template: TaskTemplate) -> TaskTemplate:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_templates (
                    id, project_id, active, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    template.id,
                    template.project_id,
                    int(template.active),
                    template.model_dump_json(),
                    template.created_at.isoformat(),
                    template.updated_at.isoformat(),
                ),
            )
        return template

    def get_task_template(
        self,
        project_id: str,
        template_id: str,
    ) -> TaskTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM task_templates
                WHERE project_id = ? AND id = ?
                """,
                (project_id, template_id),
            ).fetchone()
        return None if row is None else TaskTemplate.model_validate_json(row["payload_json"])

    def list_task_templates(
        self,
        project_id: str,
        *,
        active_only: bool = False,
    ) -> list[TaskTemplate]:
        query = "SELECT payload_json FROM task_templates WHERE project_id = ?"
        parameters: list[object] = [project_id]
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY created_at ASC, id ASC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [TaskTemplate.model_validate_json(row["payload_json"]) for row in rows]

    def create_game_day(self, game_day: GameDay) -> GameDay:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO game_days (
                    id, project_id, local_date, status, join_token,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_day.id,
                    game_day.project_id,
                    game_day.local_date.isoformat(),
                    game_day.status,
                    game_day.join_token,
                    game_day.model_dump_json(),
                    game_day.created_at.isoformat(),
                ),
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=game_day.id,
                    occurred_at=game_day.created_at,
                    type=GameEventType.DAY_CREATED,
                    message="The sustainability game day was created.",
                    source="manager",
                    evidence_kind="measured",
                    data={"local_date": game_day.local_date.isoformat()},
                ),
            )
        return game_day

    def get_game_day(
        self,
        project_id: str,
        game_day_id: str,
    ) -> GameDay | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM game_days
                WHERE project_id = ? AND id = ?
                """,
                (project_id, game_day_id),
            ).fetchone()
        return None if row is None else GameDay.model_validate_json(row["payload_json"])

    def get_game_day_by_join_token(self, join_token: str) -> GameDay | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM game_days WHERE join_token = ?",
                (join_token,),
            ).fetchone()
        return None if row is None else GameDay.model_validate_json(row["payload_json"])

    def list_game_days(self, project_id: str) -> list[GameDay]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM game_days
                WHERE project_id = ?
                ORDER BY local_date DESC, created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [GameDay.model_validate_json(row["payload_json"]) for row in rows]

    def update_game_day(self, game_day: GameDay) -> GameDay:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE game_days
                SET status = ?, payload_json = ?
                WHERE project_id = ? AND id = ?
                """,
                (
                    game_day.status,
                    game_day.model_dump_json(),
                    game_day.project_id,
                    game_day.id,
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError("Game day not found")
        return game_day

    def create_game_session(
        self,
        session: GameStaffSession,
        token_hash: str,
    ) -> GameStaffSession:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO game_staff_sessions (
                    id, game_day_id, project_id, staff_id, token_hash,
                    payload_json, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.game_day_id,
                    session.project_id,
                    session.staff_id,
                    token_hash,
                    session.model_dump_json(),
                    session.expires_at.isoformat(),
                    session.created_at.isoformat(),
                ),
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=session.game_day_id,
                    occurred_at=session.created_at,
                    type=GameEventType.STAFF_JOINED,
                    message="A staff player joined the game day.",
                    staff_id=session.staff_id,
                    source="staff",
                    evidence_kind="measured",
                ),
            )
        return session

    def get_game_session_by_token_hash(
        self,
        token_hash: str,
    ) -> GameStaffSession | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM game_staff_sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        return None if row is None else GameStaffSession.model_validate_json(row["payload_json"])

    def create_task_instances(self, tasks: list[TaskInstance]) -> list[TaskInstance]:
        with self._connect() as connection:
            for task in tasks:
                connection.execute(
                    """
                    INSERT INTO task_instances (
                        id, game_day_id, project_id, template_id, status,
                        claimed_by_staff_id, reservation_expires_at, version,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.game_day_id,
                        task.project_id,
                        task.template_id,
                        task.status,
                        task.claimed_by_staff_id,
                        task.reservation_expires_at.isoformat()
                        if task.reservation_expires_at
                        else None,
                        task.version,
                        task.model_dump_json(),
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ),
                )
                self._append_game_event_connection(
                    connection,
                    GameDayEvent(
                        seq=0,
                        game_day_id=task.game_day_id,
                        occurred_at=task.created_at,
                        type=GameEventType.TASK_RELEASED,
                        message=f"{task.label} became available.",
                        task_instance_id=task.id,
                        zone_id=task.zone_id,
                        target_id=task.equipment_id,
                        source="rules",
                        evidence_kind="assumed",
                        data={"points_available": task.base_points},
                    ),
                )
        return tasks

    def get_task_instance(
        self,
        game_day_id: str,
        task_id: str,
    ) -> TaskInstance | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM task_instances
                WHERE game_day_id = ? AND id = ?
                """,
                (game_day_id, task_id),
            ).fetchone()
        return None if row is None else TaskInstance.model_validate_json(row["payload_json"])

    def list_task_instances(self, game_day_id: str) -> list[TaskInstance]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM task_instances
                WHERE game_day_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (game_day_id,),
            ).fetchall()
        return [TaskInstance.model_validate_json(row["payload_json"]) for row in rows]

    @staticmethod
    def _append_game_event_connection(
        connection: sqlite3.Connection,
        event: GameDayEvent,
    ) -> GameDayEvent:
        row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM game_day_events WHERE game_day_id = ?",
            (event.game_day_id,),
        ).fetchone()
        stored = event.model_copy(update={"seq": int(row["next_seq"])})
        connection.execute(
            """
            INSERT INTO game_day_events (
                game_day_id, seq, occurred_at, event_type, staff_id,
                task_instance_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.game_day_id,
                stored.seq,
                stored.occurred_at.isoformat(),
                stored.type,
                stored.staff_id,
                stored.task_instance_id,
                stored.model_dump_json(),
            ),
        )
        return stored

    def append_game_event(self, event: GameDayEvent) -> GameDayEvent:
        with self._connect() as connection:
            return self._append_game_event_connection(connection, event)

    def list_game_day_events(self, game_day_id: str) -> list[GameDayEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM game_day_events
                WHERE game_day_id = ? ORDER BY seq ASC
                """,
                (game_day_id,),
            ).fetchall()
        return [GameDayEvent.model_validate_json(row["payload_json"]) for row in rows]

    @staticmethod
    def _save_task_connection(
        connection: sqlite3.Connection,
        task: TaskInstance,
        *,
        expected_status: TaskStatus,
        expected_version: int,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE task_instances
            SET status = ?, claimed_by_staff_id = ?, reservation_expires_at = ?,
                version = ?, payload_json = ?, updated_at = ?
            WHERE id = ? AND game_day_id = ? AND status = ? AND version = ?
            """,
            (
                task.status,
                task.claimed_by_staff_id,
                task.reservation_expires_at.isoformat()
                if task.reservation_expires_at
                else None,
                task.version,
                task.model_dump_json(),
                task.updated_at.isoformat(),
                task.id,
                task.game_day_id,
                expected_status,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("Task state changed; refresh and try again")

    def claim_task_instance(
        self,
        game_day_id: str,
        task_id: str,
        staff_id: str,
        *,
        claimed_at: datetime,
        reservation_expires_at: datetime,
    ) -> TaskInstance:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM task_instances WHERE game_day_id = ? AND id = ?",
                (game_day_id, task_id),
            ).fetchone()
            if row is None:
                raise ValueError("Task not found")
            current = TaskInstance.model_validate_json(row["payload_json"])
            if current.status != TaskStatus.AVAILABLE:
                raise ValueError("Task is no longer available")
            updated = current.model_copy(
                update={
                    "status": TaskStatus.CLAIMED,
                    "claimed_by_staff_id": staff_id,
                    "claimed_at": claimed_at,
                    "reservation_expires_at": reservation_expires_at,
                    "version": current.version + 1,
                    "updated_at": claimed_at,
                }
            )
            self._save_task_connection(
                connection,
                updated,
                expected_status=TaskStatus.AVAILABLE,
                expected_version=current.version,
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=game_day_id,
                    occurred_at=claimed_at,
                    type=GameEventType.TASK_CLAIMED,
                    message=f"{updated.label} was claimed.",
                    staff_id=staff_id,
                    task_instance_id=task_id,
                    zone_id=updated.zone_id,
                    target_id=updated.equipment_id,
                    source="staff",
                    evidence_kind="measured",
                ),
            )
        return updated

    def release_task_instance(
        self,
        game_day_id: str,
        task_id: str,
        staff_id: str,
        *,
        released_at: datetime,
    ) -> TaskInstance:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM task_instances WHERE game_day_id = ? AND id = ?",
                (game_day_id, task_id),
            ).fetchone()
            if row is None:
                raise ValueError("Task not found")
            current = TaskInstance.model_validate_json(row["payload_json"])
            if current.status != TaskStatus.CLAIMED or current.claimed_by_staff_id != staff_id:
                raise ValueError("Only the current claimant may release this task")
            updated = current.model_copy(
                update={
                    "status": TaskStatus.AVAILABLE,
                    "claimed_by_staff_id": None,
                    "claimed_at": None,
                    "reservation_expires_at": None,
                    "version": current.version + 1,
                    "updated_at": released_at,
                }
            )
            self._save_task_connection(
                connection,
                updated,
                expected_status=TaskStatus.CLAIMED,
                expected_version=current.version,
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=game_day_id,
                    occurred_at=released_at,
                    type=GameEventType.TASK_RELEASED_BY_STAFF,
                    message=f"{updated.label} returned to the task pool.",
                    staff_id=staff_id,
                    task_instance_id=task_id,
                    zone_id=updated.zone_id,
                    target_id=updated.equipment_id,
                    source="staff",
                    evidence_kind="measured",
                ),
            )
        return updated

    def complete_task_instance(
        self,
        game_day_id: str,
        task_id: str,
        staff_id: str,
        *,
        completed_at: datetime,
        points: int,
        score_reason: str,
        scoring_version: str,
    ) -> TaskInstance:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM task_instances WHERE game_day_id = ? AND id = ?",
                (game_day_id, task_id),
            ).fetchone()
            if row is None:
                raise ValueError("Task not found")
            current = TaskInstance.model_validate_json(row["payload_json"])
            if current.status != TaskStatus.CLAIMED or current.claimed_by_staff_id != staff_id:
                raise ValueError("Only the current claimant may complete this task")
            updated = current.model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "completed_at": completed_at,
                    "reservation_expires_at": None,
                    "verification_status": VerificationStatus.SELF_CONFIRMED,
                    "points_awarded": points,
                    "scoring_version": scoring_version,
                    "version": current.version + 1,
                    "updated_at": completed_at,
                }
            )
            self._save_task_connection(
                connection,
                updated,
                expected_status=TaskStatus.CLAIMED,
                expected_version=current.version,
            )
            score = ScoreEntry(
                id=f"score_{uuid4().hex[:12]}",
                game_day_id=game_day_id,
                project_id=updated.project_id,
                staff_id=staff_id,
                task_instance_id=task_id,
                points=points,
                reason=score_reason,
                scoring_version=scoring_version,
                created_at=completed_at,
            )
            connection.execute(
                """
                INSERT INTO score_entries (
                    id, game_day_id, project_id, staff_id, task_instance_id,
                    points, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.id,
                    score.game_day_id,
                    score.project_id,
                    score.staff_id,
                    score.task_instance_id,
                    score.points,
                    score.model_dump_json(),
                    score.created_at.isoformat(),
                ),
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=game_day_id,
                    occurred_at=completed_at,
                    type=GameEventType.TASK_COMPLETED,
                    message=f"{updated.label} was completed.",
                    staff_id=staff_id,
                    task_instance_id=task_id,
                    zone_id=updated.zone_id,
                    target_id=updated.equipment_id,
                    source="staff",
                    evidence_kind="measured",
                    data={"verification_status": str(updated.verification_status)},
                ),
            )
            self._append_game_event_connection(
                connection,
                GameDayEvent(
                    seq=0,
                    game_day_id=game_day_id,
                    occurred_at=completed_at,
                    type=GameEventType.POINTS_AWARDED,
                    message=f"{points} individual points were awarded.",
                    staff_id=staff_id,
                    task_instance_id=task_id,
                    source="rules",
                    evidence_kind="derived",
                    data={
                        "points": points,
                        "reason": score_reason,
                        "scoring_version": scoring_version,
                    },
                ),
            )
        return updated

    def list_score_entries(self, game_day_id: str) -> list[ScoreEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM score_entries
                WHERE game_day_id = ? ORDER BY created_at ASC, id ASC
                """,
                (game_day_id,),
            ).fetchall()
        return [ScoreEntry.model_validate_json(row["payload_json"]) for row in rows]

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
