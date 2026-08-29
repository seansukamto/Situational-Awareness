from __future__ import annotations

import time

from fastapi import APIRouter

from .models import (
    AIStatusResponse,
    AITestRequest,
    AITestResponse,
    AgentObservation,
    AgentProposal,
    AgentProposalAction,
)
from .providers import ProviderUnavailable, build_agent_provider, configured_provider_status


router = APIRouter(prefix="/api/ai", tags=["agent intelligence"])


def test_observation() -> AgentObservation:
    return AgentObservation(
        current_minute=1320,
        scenario_id="provider-connection-test",
        actor_kind="staff",
        agent_id="connection_test_agent",
        agent_label="Connection test agent",
        role_or_segment="manager",
        zone_id="checkout",
        zone_state={"zone_label": "Checkout", "store_open": False, "equipment": []},
        nearby_agents=[],
        nearby_equipment=[],
        customer_count=0,
        permitted_actions=[AgentProposalAction.WAIT],
        permitted_target_ids=[],
        traits={"rule_compliance": 1},
        operating_state={"fatigue": 0, "workload": 0, "time_pressure": 0},
        recent_memories=[],
        memory_summary="",
        sustainability_intervention={"id": "connection-test", "label": "None"},
        game_master_constraints=["Return a public, structured wait proposal only."],
        deterministic_fallback=AgentProposal(
            action=AgentProposalAction.WAIT,
            public_reason="The deterministic connection test waits without changing state.",
            confidence=1,
        ),
    )


@router.get("/status", response_model=AIStatusResponse)
def ai_status() -> AIStatusResponse:
    return configured_provider_status()


@router.post("/test", response_model=AITestResponse)
def test_ai_provider(request: AITestRequest) -> AITestResponse:
    provider = build_agent_provider(
        request.mode,
        model=request.model,
        timeout_seconds=request.timeout_seconds,
    )
    started = time.perf_counter()
    try:
        result = provider.propose(test_observation())
        return AITestResponse(
            success=True,
            mode=request.mode,
            provider=provider.name,
            model=provider.model,
            latency_ms=round((time.perf_counter() - started) * 1_000, 3),
            proposal=result.proposal,
        )
    except ProviderUnavailable as exc:
        return AITestResponse(
            success=False,
            mode=request.mode,
            provider=provider.name,
            model=provider.model,
            latency_ms=round((time.perf_counter() - started) * 1_000, 3),
            error=str(exc),
        )
    except Exception:
        return AITestResponse(
            success=False,
            mode=request.mode,
            provider=provider.name,
            model=provider.model,
            latency_ms=round((time.perf_counter() - started) * 1_000, 3),
            error="The configured provider did not return a valid structured proposal",
        )
