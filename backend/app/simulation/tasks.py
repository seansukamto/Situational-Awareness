from __future__ import annotations

from .models import Agent, Criticality, Equipment, Store


def authorized_shutdown_tasks(store: Store) -> list[tuple[Agent, Equipment]]:
    """Return the unique, assigned tasks that staff may safely perform.

    This is the shared task boundary for simulation metrics and staff handoff.
    Protected loads and assignments outside an agent's role authority are
    excluded even if a malformed store configuration references them.
    """

    equipment_by_id = {item.id: item for item in store.equipment}
    tasks: list[tuple[Agent, Equipment]] = []
    seen: set[str] = set()
    for agent in store.agents:
        for equipment_id in agent.assigned_equipment_ids:
            if equipment_id in seen:
                continue
            equipment = equipment_by_id[equipment_id]
            if equipment.criticality == Criticality.PROTECTED:
                continue
            if agent.role not in equipment.switchable_by_roles:
                continue
            seen.add(equipment_id)
            tasks.append((agent, equipment))
    return tasks
