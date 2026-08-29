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
