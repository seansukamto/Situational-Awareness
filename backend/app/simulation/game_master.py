from __future__ import annotations

import math
import random
from collections import defaultdict
from copy import deepcopy

from ..agents import (
    AgentDecisionAudit,
    AgentDecisionResult,
    AgentMode,
    AgentObservation,
    AgentProposal,
    AgentProposalAction,
    AgentProviderLimits,
    BudgetedAgentProvider,
    DeterministicAgentProvider,
)
from .models import (
    ActionProposal,
    ActionType,
    Agent,
    ComparisonMetric,
    Criticality,
    Customer,
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
from .tasks import authorized_shutdown_tasks


GAME_MASTER_RULES_VERSION = "green-close-rules-2026.08"
GAME_MASTER_RULES = (
    {
        "id": "protected_loads",
        "label": "Protected loads stay active",
        "description": "Protected equipment cannot be switched off by any agent.",
    },
    {
        "id": "role_authorization",
        "label": "Role authorization enforced",
        "description": "Only roles assigned to an equipment load may operate it.",
    },
    {
        "id": "customer_presence",
        "label": "Customer-facing loads guarded",
        "description": "Customer-facing equipment stays active until every consumer exits.",
    },
    {
        "id": "immutable_snapshot",
        "label": "Historical inputs locked",
        "description": "A replay always uses the configuration and evidence stored with its run.",
    },
)


class GameMaster:
    """Owns time, rules, world state, resource integration, and the event log."""

    def __init__(
        self,
        store: Store,
        scenario: Scenario,
        seed: int = 42,
        *,
        agent_provider: BudgetedAgentProvider | None = None,
    ):
        self.store = deepcopy(store)
        self.scenario = deepcopy(scenario)
        self.seed = seed
        self.random = random.Random(seed)
        self.events: list[SimulationEvent] = []
        self.seq = 0
        self.customer_count = sum(customer.active for customer in self.store.customers)
        self.total_kwh = 0.0
        self.after_hours_kwh = 0.0
        self.rejected_actions = 0
        self.customer_service_incidents = 0
        self.completed_equipment_ids: set[str] = set()
        self.agent_provider = agent_provider or BudgetedAgentProvider(
            DeterministicAgentProvider(),
            AgentProviderLimits(),
        )
        self.agent_decisions: list[AgentDecisionAudit] = []
        self._recent_memories: dict[str, list[str]] = defaultdict(list)
        self._memory_summaries: dict[str, str] = defaultdict(str)

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
            agent_decisions=self.agent_decisions,
            provider_usage=self.agent_provider.usage(),
        )

    def _update_environment(self, minute: int) -> None:
        closing = self.store.closing_minute
        previous = self.customer_count
        if minute == closing:
            self._emit(minute, EventType.STORE_CLOSED, "The store has closed to new customers.")

        active_customers = [customer for customer in self.store.customers if customer.active]
        decision_step = max(0, minute - self.scenario.start_minute) // self.scenario.tick_minutes
        external_customer_index = (
            decision_step % len(active_customers) if active_customers else -1
        )
        for active_index, customer in enumerate(active_customers):
            if not customer.active:
                continue
            draw = random.Random(f"{self.seed}:{minute}:{customer.id}:customer").random()
            minutes_after_close = minute - closing
            should_exit = minutes_after_close >= 15 or (
                minutes_after_close >= 0
                and draw < min(0.85, 0.25 + minutes_after_close / 18)
            )
            target_zone = self._customer_target_zone(customer.id, minute)
            fallback = AgentProposal(
                action=(
                    AgentProposalAction.EXIT
                    if should_exit
                    else AgentProposalAction.MOVE
                ),
                destination=None if should_exit else target_zone,
                public_reason=(
                    "The deterministic dwell-time rule indicates that the consumer should exit."
                    if should_exit
                    else "The deterministic shopping path advances to the next valid store zone."
                ),
                confidence=1,
            )
            observation = self._consumer_observation(customer, minute, fallback)
            allow_external = (
                self.agent_provider.mode != AgentMode.DETERMINISTIC
                and decision_step % 2 == 0
                and active_index == external_customer_index
            )
            decision = self._request_decision(
                observation,
                minute,
                allow_external=allow_external,
            )
            accepted, outcome = self._validate_public_proposal(
                observation,
                decision.proposal,
                minute,
            )
            if accepted:
                self._emit_action_ruling(
                    minute,
                    customer.id,
                    decision,
                    accepted=True,
                    outcome=outcome,
                )
                self._apply_customer_proposal(customer, decision.proposal, minute)
            else:
                self.rejected_actions += 1
                self._emit_action_ruling(
                    minute,
                    customer.id,
                    decision,
                    accepted=False,
                    outcome=outcome,
                )
            self._record_decision(observation, decision, accepted, outcome, minute)

        self.customer_count = sum(customer.active for customer in self.store.customers)

        if self.customer_count != previous:
            self._emit(
                minute,
                EventType.CUSTOMER_COUNT_CHANGED,
                f"Customer count changed to {self.customer_count}.",
                data={"customer_count": self.customer_count},
            )

    def _customer_target_zone(self, customer_id: str, minute: int) -> str:
        if minute >= self.store.closing_minute:
            return "checkout"
        paths = {
            "customer_01": ["sales_floor", "checkout"],
            "customer_02": ["display_wall", "sales_floor"],
            "customer_03": ["sales_floor", "display_wall"],
            "customer_04": ["display_wall", "checkout"],
        }
        options = paths.get(customer_id, ["sales_floor"])
        step = max(0, minute - self.scenario.start_minute) // self.scenario.tick_minutes
        return options[step % len(options)]

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
            fallback = AgentProposal(
                action=AgentProposalAction.OPERATE_EQUIPMENT,
                target_id=target.id,
                public_reason="The deterministic closing policy selects the next assigned load.",
                confidence=1,
            )
            observation = self._staff_observation(agent, minute, fallback, outstanding)
            decision = self._request_decision(observation, minute)
            accepted, outcome = self._validate_public_proposal(
                observation,
                decision.proposal,
                minute,
            )
            self._emit_action_ruling(
                minute,
                agent.id,
                decision,
                accepted=accepted,
                outcome=outcome,
            )
            if accepted:
                self._apply_staff_proposal(agent, decision.proposal, minute)
            else:
                self.rejected_actions += 1
            self._record_decision(observation, decision, accepted, outcome, minute)

    def _staff_observation(
        self,
        agent: Agent,
        minute: int,
        fallback: AgentProposal,
        outstanding: list[str],
    ) -> AgentObservation:
        return AgentObservation(
            current_minute=minute,
            scenario_id=self.scenario.id,
            actor_kind="staff",
            agent_id=agent.id,
            agent_label=agent.label,
            role_or_segment=str(agent.role),
            zone_id=agent.zone_id,
            zone_state=self._zone_state(agent.zone_id, minute),
            nearby_agents=self._nearby_agents(agent.zone_id, agent.id),
            nearby_equipment=self._nearby_equipment(agent.zone_id, outstanding),
            customer_count=self.customer_count,
            permitted_actions=list(AgentProposalAction),
            permitted_target_ids=(
                outstanding
                + [customer.id for customer in self.store.customers if customer.active]
                + [item.id for item in self.store.agents if item.id != agent.id]
            )[:16],
            traits={key: float(value) for key, value in agent.traits.model_dump().items()},
            operating_state={
                "fatigue": agent.fatigue,
                "workload": agent.workload,
                "time_pressure": 0.7 if self.customer_count else 0.15,
                "checklist_completed": agent.checklist_completed,
                "shift_ended": agent.shift_ended,
            },
            recent_memories=self._recent_memories[agent.id],
            memory_summary=self._memory_summaries[agent.id],
            sustainability_intervention=self.scenario.intervention.model_dump(mode="json"),
            game_master_constraints=[rule["description"] for rule in GAME_MASTER_RULES],
            deterministic_fallback=fallback,
        )

    def _consumer_observation(
        self,
        customer: Customer,
        minute: int,
        fallback: AgentProposal,
    ) -> AgentObservation:
        return AgentObservation(
            current_minute=minute,
            scenario_id=self.scenario.id,
            actor_kind="consumer",
            agent_id=customer.id,
            agent_label=customer.label,
            role_or_segment=str(customer.segment),
            zone_id=customer.zone_id,
            zone_state=self._zone_state(customer.zone_id, minute),
            nearby_agents=self._nearby_agents(customer.zone_id, customer.id),
            nearby_equipment=self._nearby_equipment(customer.zone_id, []),
            customer_count=self.customer_count,
            permitted_actions=[
                AgentProposalAction.MOVE,
                AgentProposalAction.WAIT,
                AgentProposalAction.EXIT,
            ],
            permitted_target_ids=[zone.id for zone in self.store.zones] + ["exit"],
            traits={},
            operating_state={
                "satisfaction": customer.satisfaction,
                "active": customer.active,
                "minutes_after_close": minute - self.store.closing_minute,
            },
            recent_memories=self._recent_memories[customer.id],
            memory_summary=self._memory_summaries[customer.id],
            sustainability_intervention=self.scenario.intervention.model_dump(mode="json"),
            game_master_constraints=[rule["description"] for rule in GAME_MASTER_RULES],
            deterministic_fallback=fallback,
        )

    def _zone_state(self, zone_id: str, minute: int) -> dict:
        zone = next((item for item in self.store.zones if item.id == zone_id), None)
        return {
            "zone_label": zone.label if zone else "Store exit",
            "store_open": self.store.opening_minute <= minute < self.store.closing_minute,
            "equipment": [
                {
                    "id": item.id,
                    "state": str(item.state),
                    "criticality": str(item.criticality),
                    "customer_facing": item.customer_facing,
                }
                for item in self.store.equipment
                if item.zone_id == zone_id
            ][:8],
        }

    def _nearby_agents(self, zone_id: str, excluded_id: str) -> list[dict]:
        staff = [
            {"id": item.id, "kind": "staff", "role": str(item.role)}
            for item in self.store.agents
            if item.id != excluded_id and item.zone_id == zone_id and not item.shift_ended
        ]
        consumers = [
            {"id": item.id, "kind": "consumer", "segment": str(item.segment)}
            for item in self.store.customers
            if item.id != excluded_id and item.zone_id == zone_id and item.active
        ]
        return (staff + consumers)[:8]

    def _nearby_equipment(
        self,
        zone_id: str,
        required_ids: list[str],
    ) -> list[dict]:
        required = set(required_ids)
        candidates = [
            item
            for item in self.store.equipment
            if item.zone_id == zone_id or item.id in required
        ]
        return [
            {
                "id": item.id,
                "label": item.label,
                "zone_id": item.zone_id,
                "state": str(item.state),
                "criticality": str(item.criticality),
                "customer_facing": item.customer_facing,
            }
            for item in candidates[:8]
        ]

    def _request_decision(
        self,
        observation: AgentObservation,
        minute: int,
        *,
        allow_external: bool = True,
    ) -> AgentDecisionResult:
        self._emit(
            minute,
            EventType.AGENT_OBSERVATION,
            f"{observation.agent_label} reached a bounded decision point.",
            agent_id=observation.agent_id,
            data={
                **observation.audit_summary(),
                "requested_mode": str(self.agent_provider.mode),
                "external_provider_eligible": allow_external,
            },
        )
        decision = self.agent_provider.decide(
            observation,
            allow_external=allow_external,
        )
        if decision.failure_kind:
            event_type = (
                EventType.PROVIDER_BUDGET_EXHAUSTED
                if decision.failure_kind == "budget_exhausted"
                else EventType.PROVIDER_FAILURE
            )
            self._emit(
                minute,
                event_type,
                decision.failure_message or "The selected provider was unavailable.",
                agent_id=observation.agent_id,
                data={
                    "requested_mode": str(self.agent_provider.mode),
                    "failure_kind": decision.failure_kind,
                    "fallback": "deterministic",
                },
            )
            self._emit(
                minute,
                EventType.PROVIDER_FALLBACK,
                f"{observation.agent_label} used the deterministic fallback proposal.",
                agent_id=observation.agent_id,
                data={"generated_by_ai": False, "failure_kind": decision.failure_kind},
            )
        self._emit(
            minute,
            EventType.AGENT_PROPOSAL,
            f"{observation.agent_label} proposed {str(decision.proposal.action).replace('_', ' ')}.",
            agent_id=observation.agent_id,
            target_id=decision.proposal.target_id,
            data={
                **decision.proposal.model_dump(mode="json"),
                "provider": decision.provider,
                "model": decision.model,
                "generated_by_ai": decision.generated_by_ai,
                "fallback_used": decision.fallback_used,
                "cache_hit": decision.cache_hit,
                "latency_ms": decision.latency_ms,
                "input_tokens": decision.input_tokens,
                "output_tokens": decision.output_tokens,
                "estimated_cost_usd": decision.estimated_cost_usd,
            },
        )
        return decision

    def _validate_public_proposal(
        self,
        observation: AgentObservation,
        proposal: AgentProposal,
        minute: int,
    ) -> tuple[bool, str]:
        if proposal.action not in observation.permitted_actions:
            return False, "The action is outside this agent's permitted action set."
        if minute < self.store.opening_minute or minute > self.scenario.end_minute:
            return False, "The action is outside the authoritative store timeline."
        if observation.actor_kind == "consumer":
            customer = next(
                (item for item in self.store.customers if item.id == observation.agent_id),
                None,
            )
            if customer is None or not customer.active:
                return False, "The consumer is no longer active in the store."
            if proposal.action == AgentProposalAction.WAIT:
                return True, "The Game Master accepted a no-op wait decision."
            if proposal.action == AgentProposalAction.EXIT:
                if minute < self.store.closing_minute:
                    return False, "Consumers exit through this closing model only after close."
                return True, "The Game Master accepted the consumer exit."
            if proposal.action == AgentProposalAction.MOVE:
                zone_ids = {zone.id for zone in self.store.zones}
                if proposal.destination not in zone_ids:
                    return False, "The requested destination is not a valid store zone."
                if (
                    minute >= self.store.closing_minute
                    and proposal.destination != "checkout"
                ):
                    return False, "After close, consumers may only move toward checkout."
                return True, "The Game Master accepted movement to a valid store zone."
            return False, "Consumers cannot perform the proposed staff action."

        agent = next(
            (item for item in self.store.agents if item.id == observation.agent_id),
            None,
        )
        if agent is None or agent.shift_ended:
            return False, "The staff agent is not active in this simulation."
        if proposal.action == AgentProposalAction.OPERATE_EQUIPMENT:
            internal = ActionProposal(
                agent_id=agent.id,
                action=ActionType.TOGGLE_EQUIPMENT,
                target_id=proposal.target_id,
                desired_state=EquipmentState.OFF,
                reason_code="agent_provider_proposal",
            )
            accepted, reason = self._validate(internal)
            return (
                (True, "The Game Master accepted the authorized equipment transition.")
                if accepted
                else (False, reason)
            )
        if proposal.action == AgentProposalAction.MOVE:
            if proposal.destination not in {zone.id for zone in self.store.zones}:
                return False, "The requested destination is not a valid store zone."
            return True, "The Game Master accepted movement to a valid store zone."
        if proposal.action == AgentProposalAction.ASSIST_CUSTOMER:
            customer = next(
                (
                    item
                    for item in self.store.customers
                    if item.id == proposal.target_id and item.active
                ),
                None,
            )
            if customer is None:
                return False, "The requested consumer is not active in the store."
            return True, "The Game Master accepted the customer-assistance action."
        if proposal.action == AgentProposalAction.REMIND_STAFF:
            if str(agent.role) != "manager":
                return False, "Only the shift manager may issue a staff reminder."
            target = next(
                (
                    item
                    for item in self.store.agents
                    if item.id == proposal.target_id and not item.shift_ended
                ),
                None,
            )
            if target is None or target.id == agent.id:
                return False, "The reminder target is not an active colleague."
            return True, "The Game Master accepted the manager reminder."
        if proposal.action == AgentProposalAction.WAIT:
            return True, "The Game Master accepted a no-op wait decision."
        if proposal.action == AgentProposalAction.EXIT:
            if minute < self.store.closing_minute or not agent.checklist_completed:
                return False, "Staff may exit only after close with a completed checklist."
            return True, "The Game Master accepted the completed shift exit."
        return False, "The action is unsupported by the authoritative Game Master."

    def _emit_action_ruling(
        self,
        minute: int,
        agent_id: str,
        decision: AgentDecisionResult,
        *,
        accepted: bool,
        outcome: str,
    ) -> None:
        proposal = decision.proposal
        self._emit(
            minute,
            EventType.ACTION_ACCEPTED if accepted else EventType.ACTION_REJECTED,
            outcome,
            agent_id=agent_id,
            target_id=proposal.target_id,
            data={
                "action": str(proposal.action),
                "destination": proposal.destination,
                "public_reason": proposal.public_reason,
                "confidence": proposal.confidence,
                "provider": decision.provider,
                "model": decision.model,
                "generated_by_ai": decision.generated_by_ai,
                "fallback_used": decision.fallback_used,
            },
        )

    def _apply_customer_proposal(
        self,
        customer: Customer,
        proposal: AgentProposal,
        minute: int,
    ) -> None:
        if proposal.action == AgentProposalAction.WAIT:
            return
        previous_position = customer.position.model_copy()
        if proposal.action == AgentProposalAction.EXIT:
            customer.active = False
            customer.zone_id = "exit"
            customer.position = customer.position.model_copy(update={"x": -6.2, "z": -3.4})
            self._emit(
                minute,
                EventType.CUSTOMER_EXITED,
                f"{customer.label} left the store.",
                agent_id=customer.id,
                data={
                    "from": previous_position.model_dump(),
                    "to": customer.position.model_dump(),
                    "segment": customer.segment,
                },
            )
            return
        zone = next(item for item in self.store.zones if item.id == proposal.destination)
        customer.zone_id = zone.id
        jitter = random.Random(f"{self.seed}:{minute}:{customer.id}:position")
        customer.position = zone.center.model_copy(
            update={
                "x": zone.center.x + jitter.uniform(-zone.width * 0.25, zone.width * 0.25),
                "z": zone.center.z + jitter.uniform(-zone.depth * 0.25, zone.depth * 0.25),
            }
        )
        if customer.position != previous_position:
            self._emit(
                minute,
                EventType.CUSTOMER_MOVED,
                f"{customer.label} moved through {zone.label}.",
                agent_id=customer.id,
                data={
                    "from": previous_position.model_dump(),
                    "to": customer.position.model_dump(),
                    "zone_id": zone.id,
                    "segment": customer.segment,
                },
            )

    def _apply_staff_proposal(
        self,
        agent: Agent,
        proposal: AgentProposal,
        minute: int,
    ) -> None:
        if proposal.action in {AgentProposalAction.WAIT, AgentProposalAction.REMIND_STAFF}:
            return
        if proposal.action == AgentProposalAction.OPERATE_EQUIPMENT:
            self._apply_toggle(agent, self._equipment(proposal.target_id or ""), minute)
            return
        if proposal.action == AgentProposalAction.MOVE:
            zone = next(item for item in self.store.zones if item.id == proposal.destination)
            previous = agent.position.model_copy()
            agent.zone_id = zone.id
            agent.position = zone.center.model_copy()
            self._emit(
                minute,
                EventType.AGENT_MOVED,
                f"{agent.label} moved to {zone.label}.",
                agent_id=agent.id,
                data={
                    "from": previous.model_dump(),
                    "to": agent.position.model_dump(),
                    "zone_id": zone.id,
                },
            )
            return
        if proposal.action == AgentProposalAction.ASSIST_CUSTOMER:
            customer = next(
                item for item in self.store.customers if item.id == proposal.target_id
            )
            previous = agent.position.model_copy()
            agent.zone_id = customer.zone_id
            agent.position = customer.position.model_copy()
            agent.minutes_spent_on_intervention += 0.5
            customer.satisfaction = min(1, customer.satisfaction + 0.02)
            self._emit(
                minute,
                EventType.AGENT_MOVED,
                f"{agent.label} moved to assist {customer.label}.",
                agent_id=agent.id,
                target_id=customer.id,
                data={
                    "from": previous.model_dump(),
                    "to": agent.position.model_dump(),
                    "zone_id": customer.zone_id,
                },
            )
            return
        if proposal.action == AgentProposalAction.EXIT:
            agent.shift_ended = True
            self._emit(
                minute,
                EventType.SHIFT_ENDED,
                f"{agent.label} ended their shift.",
                agent_id=agent.id,
                data={"checklist_completed": agent.checklist_completed},
            )

    def _record_decision(
        self,
        observation: AgentObservation,
        decision: AgentDecisionResult,
        accepted: bool,
        outcome: str,
        minute: int,
    ) -> None:
        memory = (
            f"{minute}: proposed {str(decision.proposal.action)}; "
            f"{'accepted' if accepted else 'rejected'} — {outcome}"
        )[:240]
        memories = self._recent_memories[observation.agent_id]
        memories.append(memory)
        if len(memories) > 4:
            older = memories.pop(0)
            combined = " | ".join(
                value
                for value in [self._memory_summaries[observation.agent_id], older]
                if value
            )
            self._memory_summaries[observation.agent_id] = combined[-480:]
        self.agent_decisions.append(
            AgentDecisionAudit(
                event_seq=self.seq,
                at_minute=minute,
                scenario_id=self.scenario.id,
                actor_kind=observation.actor_kind,
                agent_id=observation.agent_id,
                observation=observation.audit_summary(),
                proposal=decision.proposal,
                accepted=accepted,
                outcome=outcome,
                provider=decision.provider,
                model=decision.model,
                generated_by_ai=decision.generated_by_ai,
                fallback_used=decision.fallback_used,
                failure_kind=decision.failure_kind,
                public_reason=decision.proposal.public_reason,
                latency_ms=decision.latency_ms,
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                estimated_cost_usd=decision.estimated_cost_usd,
                memory_summary=self._memory_summaries[observation.agent_id],
            )
        )

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
        agent = next(
            (item for item in self.store.agents if item.id == proposal.agent_id),
            None,
        )
        if agent is None:
            return False, "The Game Master rejected an action from an unknown staff agent."
        if proposal.action != ActionType.TOGGLE_EQUIPMENT:
            return False, "The Game Master rejected an unsupported equipment action."
        if proposal.target_id is None:
            return False, "The Game Master rejected an action without a target."
        target = next(
            (item for item in self.store.equipment if item.id == proposal.target_id),
            None,
        )
        if target is None:
            return False, "The Game Master rejected an unknown equipment target."
        if target.criticality == Criticality.PROTECTED:
            return False, f"{target.label} is protected and must remain active."
        if agent.role not in target.switchable_by_roles:
            return False, f"{agent.label} is not permitted to operate {target.label}."
        if target.customer_facing and self.customer_count > 0:
            return False, f"{target.label} must remain active while customers are present."
        if proposal.desired_state == target.state:
            return False, f"{target.label} is already {target.state}."
        if proposal.desired_state != EquipmentState.OFF:
            return False, "This closing scenario only permits validated off transitions."
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
        eligible_equipment_ids = {
            equipment.id for _, equipment in authorized_shutdown_tasks(self.store)
        }
        completed = len(self.completed_equipment_ids.intersection(eligible_equipment_ids))
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
            shutdown_tasks_total=len(eligible_equipment_ids),
            shutdown_tasks_completed=completed,
            completion_rate=round(completed / max(len(eligible_equipment_ids), 1), 4),
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
