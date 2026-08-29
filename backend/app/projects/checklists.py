from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .models import ChecklistSession, ChecklistTask, Project


def create_checklist(project: Project) -> ChecklistSession:
    equipment_by_id = {item.id: item for item in project.store.equipment}
    zones_by_id = {item.id: item for item in project.store.zones}
    tasks: list[ChecklistTask] = []
    seen: set[str] = set()
    for agent in project.store.agents:
        for equipment_id in agent.assigned_equipment_ids:
            if equipment_id in seen:
                continue
            equipment = equipment_by_id[equipment_id]
            seen.add(equipment_id)
            tasks.append(
                ChecklistTask(
                    id=f"task_{equipment.id}",
                    equipment_id=equipment.id,
                    label=equipment.label,
                    zone_label=zones_by_id[equipment.zone_id].label,
                    assigned_role=agent.role.replace("_", " ").title(),
                    criticality=equipment.criticality,
                )
            )
    created_at = datetime.now(UTC)
    return ChecklistSession(
        id=f"checklist_{uuid4().hex[:12]}",
        token=secrets.token_urlsafe(18),
        project_id=project.id,
        store_name=project.name,
        tasks=tasks,
        safety_note=(
            "Only complete the assigned items. Refrigeration, emergency, security, and other "
            "protected systems are intentionally excluded."
        ),
        created_at=created_at,
        expires_at=created_at + timedelta(hours=24),
    )


def complete_task(checklist: ChecklistSession, task_id: str) -> ChecklistSession:
    completed_at = datetime.now(UTC)
    tasks = [
        task.model_copy(update={"completed_at": completed_at}) if task.id == task_id else task
        for task in checklist.tasks
    ]
    if not any(task.id == task_id for task in checklist.tasks):
        raise ValueError("Checklist task not found")
    status = "completed" if all(task.completed_at for task in tasks) else "open"
    return checklist.model_copy(update={"tasks": tasks, "status": status})
