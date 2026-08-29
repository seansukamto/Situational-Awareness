from __future__ import annotations

from .models import EventExplanation, EventType, SimulationEvent


def explain_event(event: SimulationEvent) -> EventExplanation:
    base = {
        "event_seq": event.seq,
        "summary": event.message,
    }
    grounding = [
        f"event #{event.seq}",
        f"simulation minute {event.at_minute}",
        f"event type {event.type}",
    ]
    if event.type == EventType.EQUIPMENT_STATE_CHANGED:
        return EventExplanation(
            **base,
            rationale=(
                "The Game Master accepted the staff proposal after the target passed protected-load, "
                "role-authority, customer-presence, and current-state checks."
            ),
            rules_checked=[
                "protected equipment remains active",
                "staff role may operate target",
                "no customer-facing load is disabled while occupied",
                "target state actually changes",
            ],
            grounded_in=grounding
            + [f"target {event.target_id}", f"state transition {event.data.get('from')} → {event.data.get('to')}"],
            counterfactual="The action would have been rejected if any safety or occupancy rule failed.",
            confidence="high",
        )
    if event.type == EventType.ACTION_REJECTED:
        return EventExplanation(
            **base,
            rationale="The proposed action conflicted with an authoritative operating constraint.",
            rules_checked=["equipment criticality", "role authority", "customer presence", "target state"],
            grounded_in=grounding,
            counterfactual="The proposal would be accepted only after the blocking condition cleared.",
            confidence="high",
        )
    if event.type == EventType.ACTION_ACCEPTED:
        source = "generative provider" if event.data.get("generated_by_ai") else "deterministic provider"
        return EventExplanation(
            **base,
            rationale=(
                f"The {source} proposed a public action and the Game Master accepted it "
                "after applying the authoritative constraints."
            ),
            rules_checked=[
                "permitted action schema",
                "valid actor and target",
                "store timeline",
                "authoritative state constraints",
            ],
            grounded_in=grounding
            + [f"public reason {event.data.get('public_reason', 'not supplied')}"],
            counterfactual="A failed rule would have produced an auditable rejection without mutating state.",
            confidence="high",
        )
    if event.type == EventType.AGENT_OBSERVATION:
        return EventExplanation(
            **base,
            rationale=(
                "The agent received a bounded observation containing only the current store context, "
                "permitted actions, concise memory, and Game Master constraints."
            ),
            rules_checked=["bounded observation", "no credentials", "no personal data"],
            grounded_in=grounding,
            counterfactual="No provider is called outside a recorded decision point.",
            confidence="high",
        )
    if event.type == EventType.AGENT_PROPOSAL:
        generated = bool(event.data.get("generated_by_ai"))
        return EventExplanation(
            **base,
            rationale=(
                "A generative provider returned this strict public proposal."
                if generated
                else "The deterministic provider returned this reproducible public proposal."
            ),
            rules_checked=["strict proposal schema", "public rationale only", "Game Master review required"],
            grounded_in=grounding
            + [
                f"provider {event.data.get('provider')}",
                f"public reason {event.data.get('public_reason')}",
            ],
            counterfactual="The proposal alone cannot change the store; only a later accepted ruling can.",
            confidence="high" if not generated else "medium",
        )
    if event.type in {
        EventType.PROVIDER_FAILURE,
        EventType.PROVIDER_BUDGET_EXHAUSTED,
        EventType.PROVIDER_FALLBACK,
    }:
        return EventExplanation(
            **base,
            rationale=(
                "The requested provider could not be used safely, so the decision was explicitly "
                "labelled and routed to deterministic fallback behaviour."
            ),
            rules_checked=["provider availability", "call and token budgets", "deterministic fallback"],
            grounded_in=grounding,
            counterfactual="A valid in-budget provider response would remain a proposal subject to the same rules.",
            confidence="high",
        )
    if event.type in {EventType.CUSTOMER_MOVED, EventType.CUSTOMER_EXITED}:
        return EventExplanation(
            **base,
            rationale=(
                "This consumer-agent transition updates occupancy before the next staff action is evaluated."
            ),
            rules_checked=["consumer remains active until exit", "customer-facing loads follow occupancy"],
            grounded_in=grounding,
            counterfactual="If this consumer remained inside, customer-facing shutdown tasks would stay blocked.",
            confidence="medium",
        )
    if event.type == EventType.NUDGE_SENT:
        return EventExplanation(
            **base,
            rationale="The Green Close policy delivered its configured reminder at the scheduled minute.",
            rules_checked=["intervention schedule", "scenario configuration"],
            grounded_in=grounding,
            counterfactual="The baseline run omits this clarity and social-norm intervention.",
            confidence="high",
        )
    return EventExplanation(
        **base,
        rationale="The event was emitted by the deterministic Game Master state transition.",
        rules_checked=["simulation clock", "authoritative event ordering"],
        grounded_in=grounding,
        counterfactual="Changing the seed or scenario can change later events, never this recorded replay.",
        confidence="medium",
    )
