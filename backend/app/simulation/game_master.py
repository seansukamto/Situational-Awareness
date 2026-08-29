from __future__ import annotations

import math
import random
from copy import deepcopy

from .models import (
    ActionProposal,
    ActionType,
    Agent,
    ComparisonMetric,
    Criticality,
    Equipment,
    EquipmentState,
    EventType,
    RunMetrics,
    Scenario,
    ScenarioComparison,
    SimulationEvent,
    SimulationRun,
    Store,
)


class GameMaster:
    """Owns time, rules, world state, resource integration, and the event log."""

    def __init__(self, store: Store, scenario: Scenario, seed: int = 42):
        self.store = deepcopy(store)
        self.scenario = deepcopy(scenario)
        self.seed = seed
        self.random = random.Random(seed)
        self.events: list[SimulationEvent] = []
        self.seq = 0
        self.customer_count = 4
        self.total_kwh = 0.0
        self.after_hours_kwh = 0.0
        self.rejected_actions = 0
        self.customer_service_incidents = 0
        self.completed_equipment_ids: set[str] = set()

    def run(self) -> SimulationRun:
        self._emit(
            self.scenario.start_minute,
            EventType.SIMULATION_STARTED,
            f"{self.scenario.label} simulation started.",
            data={"seed": self.seed, "scenario_id": self.scenario.id},
        )

        for minute in range(
            self.scenario.start_minute,
            self.scenario.end_minute,
            self.scenario.tick_minutes,
        ):
            self._update_environment(minute)
            self._integrate_energy(minute)
            self._advance_fatigue(minute)
            self._send_intervention_nudge(minute)
            self._run_agent_decisions(minute)

        self._end_remaining_shifts(self.scenario.end_minute)
        metrics = self._build_metrics()
        self._emit(
            self.scenario.end_minute,
            EventType.SIMULATION_COMPLETED,
            "Simulation completed with an auditable event log.",
            data={"metrics": metrics.model_dump(mode="json")},
        )
        return SimulationRun(
            id=f"{self.scenario.id}-{self.seed}",
            scenario_id=self.scenario.id,
            seed=self.seed,
            store=self.store,
            events=self.events,
            metrics=metrics,
        )

    def _update_environment(self, minute: int) -> None:
        closing = self.store.closing_minute
        previous = self.customer_count
        if minute < closing - 10:
            self.customer_count = max(1, 4 + self.random.choice([-1, 0, 0, 1]))
        elif minute < closing:
            self.customer_count = max(0, self.customer_count - self.random.choice([0, 1, 1]))
        elif minute == closing:
            self._emit(minute, EventType.STORE_CLOSED, "The store has closed to new customers.")
            self.customer_count = max(0, self.customer_count - 1)
        else:
            self.customer_count = max(0, self.customer_count - self.random.choice([0, 1, 1, 1]))

        if self.customer_count != previous:
            self._emit(
                minute,
                EventType.CUSTOMER_COUNT_CHANGED,
                f"Customer count changed to {self.customer_count}.",
                data={"customer_count": self.customer_count},
            )

    def _integrate_energy(self, minute: int) -> None:
        tick_hours = self.scenario.tick_minutes / 60
        tick_kwh = sum(item.power_kw() for item in self.store.equipment) * tick_hours
        self.total_kwh += tick_kwh
        if minute >= self.store.closing_minute:
            self.after_hours_kwh += tick_kwh

    def _advance_fatigue(self, minute: int) -> None:
        if minute < self.store.closing_minute:
            return
        for agent in self.store.agents:
            if not agent.shift_ended:
                agent.fatigue = min(1, agent.fatigue + 0.004 * agent.traits.fatigue_sensitivity)

    def _send_intervention_nudge(self, minute: int) -> None:
        intervention = self.scenario.intervention
        if intervention.reminder_minute != minute:
            return
        self._emit(
            minute,
            EventType.NUDGE_SENT,
            "Closing zones were assigned with a team progress reminder.",
            data={
                "clarity": intervention.clarity,
                "social_norm_strength": intervention.social_norm_strength,
            },
        )

    def _run_agent_decisions(self, minute: int) -> None:
        if minute < self.store.closing_minute:
            return
        for agent in self.store.agents:
            if agent.shift_ended or agent.checklist_completed:
                continue
            outstanding = [
                equipment_id
                for equipment_id in agent.assigned_equipment_ids
                if equipment_id not in self.completed_equipment_ids
            ]
            if not outstanding:
                self._complete_checklist(agent, minute)
                continue
            target = self._equipment(outstanding[0])
            if not self._should_attempt(agent, minute):
                continue
            proposal = ActionProposal(
                agent_id=agent.id,
                action=ActionType.TOGGLE_EQUIPMENT,
                target_id=target.id,
                desired_state=EquipmentState.OFF,
                reason_code="assigned_closing_task",
            )
            accepted, rejection_reason = self._validate(proposal)
            if not accepted:
                self.rejected_actions += 1
                self._emit(
                    minute,
                    EventType.ACTION_REJECTED,
                    rejection_reason,
                    agent_id=agent.id,
                    target_id=target.id,
                    data={"action": proposal.action},
                )
                continue
            self._apply_toggle(agent, target, minute)

    def _should_attempt(self, agent: Agent, minute: int) -> bool:
        intervention = self.scenario.intervention
        time_pressure = 0.7 if self.customer_count else 0.15
        overtime_pressure = max(0, minute - self.store.closing_minute) / 30
        score = (
            -2.3
            + 1.15 * agent.traits.rule_compliance
            + 0.65 * agent.traits.sustainability_motivation
            + 0.75 * intervention.clarity
            + 0.55 * intervention.social_norm_strength * agent.traits.social_susceptibility
            + 0.45 * intervention.manager_support
            - 0.75 * agent.workload
            - 0.65 * agent.fatigue * agent.traits.fatigue_sensitivity
            - 0.8 * time_pressure * agent.traits.time_pressure_sensitivity
            + 0.25 * overtime_pressure
        )
        probability = 1 / (1 + math.exp(-score))
        # A per-agent, per-tick draw keeps baseline/intervention comparisons paired.
        # The intervention changes the probability, not the underlying random event.
        paired_draw = random.Random(f"{self.seed}:{minute}:{agent.id}:attempt").random()
        return paired_draw < probability

    def _validate(self, proposal: ActionProposal) -> tuple[bool, str]:
        agent = self._agent(proposal.agent_id)
        if proposal.target_id is None:
            return False, "The Game Master rejected an action without a target."
        target = self._equipment(proposal.target_id)
        if target.criticality == Criticality.PROTECTED:
            return False, f"{target.label} is protected and must remain active."
        if agent.role not in target.switchable_by_roles:
            return False, f"{agent.label} is not permitted to operate {target.label}."
        if target.customer_facing and self.customer_count > 0:
            return False, f"{target.label} must remain active while customers are present."
        if proposal.desired_state == target.state:
            return False, f"{target.label} is already {target.state}."
        return True, ""

    def _apply_toggle(self, agent: Agent, target: Equipment, minute: int) -> None:
        old_position = agent.position.model_copy()
        agent.zone_id = target.zone_id
        agent.position = target.position.model_copy()
        self._emit(
            minute,
            EventType.AGENT_MOVED,
            f"{agent.label} moved to {target.label}.",
            agent_id=agent.id,
            target_id=target.id,
            data={
                "from": old_position.model_dump(),
                "to": target.position.model_dump(),
                "zone_id": target.zone_id,
            },
        )
        previous_state = target.state
        target.state = EquipmentState.OFF
        agent.minutes_spent_on_intervention += 0.5
        self.completed_equipment_ids.add(target.id)
        self._emit(
            minute,
            EventType.EQUIPMENT_STATE_CHANGED,
            f"{agent.label} safely switched off {target.label}.",
            agent_id=agent.id,
            target_id=target.id,
            data={"from": previous_state, "to": target.state, "power_kw": target.power_kw()},
        )

    def _complete_checklist(self, agent: Agent, minute: int) -> None:
        agent.checklist_completed = True
        agent.minutes_spent_on_intervention += 0.25
        self._emit(
            minute,
            EventType.CHECKLIST_COMPLETED,
            f"{agent.label} completed their closing checklist.",
            agent_id=agent.id,
        )

    def _end_remaining_shifts(self, minute: int) -> None:
        for agent in self.store.agents:
            if agent.shift_ended:
                continue
            agent.shift_ended = True
            self._emit(
                minute,
                EventType.SHIFT_ENDED,
                f"{agent.label} ended their shift.",
                agent_id=agent.id,
                data={"checklist_completed": agent.checklist_completed},
            )

    def _build_metrics(self) -> RunMetrics:
        eligible_equipment = [
            item for item in self.store.equipment if item.criticality == Criticality.NON_CRITICAL
        ]
        completed = len(self.completed_equipment_ids.intersection({item.id for item in eligible_equipment}))
        staff_minutes = sum(agent.minutes_spent_on_intervention for agent in self.store.agents)
        latest_action_minute = max(
            (
                event.at_minute
                for event in self.events
                if event.type in {EventType.EQUIPMENT_STATE_CHANGED, EventType.CHECKLIST_COMPLETED}
            ),
            default=self.store.closing_minute,
        )
        overtime = max(0, latest_action_minute - self.store.closing_minute)
        return RunMetrics(
            total_kwh=round(self.total_kwh, 4),
            after_hours_kwh=round(self.after_hours_kwh, 4),
            cost_sgd=round(self.total_kwh * self.store.tariff_sgd_per_kwh, 4),
            emissions_kg_co2=round(
                self.total_kwh * self.store.grid_emission_factor_kg_per_kwh, 4
            ),
            shutdown_tasks_total=len(eligible_equipment),
            shutdown_tasks_completed=completed,
            completion_rate=round(completed / max(len(eligible_equipment), 1), 4),
            staff_minutes=round(staff_minutes, 2),
            overtime_minutes=float(overtime),
            rejected_actions=self.rejected_actions,
            customer_service_incidents=self.customer_service_incidents,
        )

    def _emit(
        self,
        minute: int,
        event_type: EventType,
        message: str,
        *,
        agent_id: str | None = None,
        target_id: str | None = None,
        data: dict | None = None,
    ) -> None:
        self.seq += 1
        self.events.append(
            SimulationEvent(
                seq=self.seq,
                at_minute=minute,
                type=event_type,
                message=message,
                agent_id=agent_id,
                target_id=target_id,
                data=data or {},
            )
        )

    def _agent(self, agent_id: str) -> Agent:
        return next(item for item in self.store.agents if item.id == agent_id)

    def _equipment(self, equipment_id: str) -> Equipment:
        return next(item for item in self.store.equipment if item.id == equipment_id)

    @staticmethod
    def compare(baseline: SimulationRun, intervention: SimulationRun) -> ScenarioComparison:
        def metric(base: float, changed: float) -> ComparisonMetric:
            difference = changed - base
            percent_change = None if base == 0 else difference / base * 100
            return ComparisonMetric(
                baseline=round(base, 4),
                intervention=round(changed, 4),
                difference=round(difference, 4),
                percent_change=None if percent_change is None else round(percent_change, 2),
            )

        return ScenarioComparison(
            baseline_run=baseline,
            intervention_run=intervention,
            energy_kwh=metric(baseline.metrics.total_kwh, intervention.metrics.total_kwh),
            cost_sgd=metric(baseline.metrics.cost_sgd, intervention.metrics.cost_sgd),
            emissions_kg_co2=metric(
                baseline.metrics.emissions_kg_co2,
                intervention.metrics.emissions_kg_co2,
            ),
            completion_rate=metric(
                baseline.metrics.completion_rate,
                intervention.metrics.completion_rate,
            ),
        )
