import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.api import test_observation as provider_test_observation
from app.agents.models import (
    AgentMode,
    AgentProposal,
    AgentProposalAction,
    AgentProviderLimits,
    AgentProviderResponse,
)
from app.agents.providers import (
    AgentProvider,
    BudgetedAgentProvider,
    DeterministicAgentProvider,
    OllamaAgentProvider,
    OpenAIAgentProvider,
)
from app.main import app
from app.projects.repository import SQLiteRepository
from app.simulation import GameMaster, build_demo_store, get_scenario


class ScriptedProvider(AgentProvider):
    mode = AgentMode.OPENAI
    name = "mock-openai"
    model = "mock-structured-model"
    configuration_fingerprint = "safe-test-fingerprint"

    def __init__(self, proposal: AgentProposal):
        self.proposal = proposal
        self.observations = []

    def propose(self, observation):
        self.observations.append(observation)
        return AgentProviderResponse(
            proposal=self.proposal,
            input_tokens=25,
            output_tokens=12,
            estimated_cost_usd=0.001,
        )


class TimeoutProvider(ScriptedProvider):
    def propose(self, observation):
        raise TimeoutError("secret-bearing provider diagnostics must not persist")


class MalformedProvider(ScriptedProvider):
    def propose(self, observation):
        return {"proposal": {"action": "rewrite_store", "hidden_reasoning": "no"}}


def test_structured_proposal_rejects_unknown_actions_and_hidden_fields():
    with pytest.raises(ValidationError):
        AgentProposal.model_validate(
            {
                "action": "rewrite_store",
                "public_reason": "Invalid action",
                "confidence": 1,
            }
        )
    with pytest.raises(ValidationError):
        AgentProposal.model_validate(
            {
                "action": "wait",
                "public_reason": "Wait safely",
                "confidence": 1,
                "chain_of_thought": "must never be accepted",
            }
        )


def test_official_openai_adapter_uses_responses_structured_output_without_storage():
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "action": "wait",
                        "target_id": None,
                        "destination": None,
                        "public_reason": "Wait for the next authorized task.",
                        "confidence": 0.8,
                    }
                ),
                usage=SimpleNamespace(input_tokens=33, output_tokens=14),
            )

    provider = OpenAIAgentProvider(
        api_key="test-only-key",
        model="configured-model",
        timeout_seconds=2,
        client=SimpleNamespace(responses=FakeResponses()),
        input_cost_per_million_usd=1,
        output_cost_per_million_usd=4,
    )
    result = provider.propose(provider_test_observation())

    assert result.proposal.action == AgentProposalAction.WAIT
    assert result.input_tokens == 33
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["text"]["format"]["strict"] is True
    assert "test-only-key" not in json.dumps(calls)


def test_ollama_adapter_uses_schema_and_parses_public_proposal():
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "action": "wait",
                            "target_id": None,
                            "destination": None,
                            "public_reason": "Wait locally.",
                            "confidence": 0.7,
                        }
                    )
                },
                "prompt_eval_count": 21,
                "eval_count": 9,
            }

    class FakeClient:
        def post(self, url, json):
            requests.append((url, json))
            return FakeResponse()

    provider = OllamaAgentProvider(
        base_url="http://127.0.0.1:11434",
        model="local-model",
        timeout_seconds=2,
        client=FakeClient(),
    )
    result = provider.propose(provider_test_observation())

    assert result.proposal.action == AgentProposalAction.WAIT
    assert result.input_tokens == 21
    assert requests[0][1]["format"]["additionalProperties"] is False


def test_timeout_and_malformed_output_fall_back_with_explicit_failure():
    proposal = AgentProposal(
        action=AgentProposalAction.WAIT,
        public_reason="Mock proposal",
        confidence=0.5,
    )
    limits = AgentProviderLimits(max_calls=2, max_calls_per_agent=2)
    for provider, expected_kind in [
        (TimeoutProvider(proposal), "timeout"),
        (MalformedProvider(proposal), "invalid_output"),
    ]:
        result = BudgetedAgentProvider(provider, limits).decide(
            provider_test_observation()
        )
        assert result.generated_by_ai is False
        assert result.fallback_used is True
        assert result.provider == "deterministic"
        assert result.failure_kind == expected_kind
        assert "secret-bearing" not in (result.failure_message or "")


def test_call_budget_exhaustion_stops_provider_calls_and_falls_back():
    provider = ScriptedProvider(
        AgentProposal(
            action=AgentProposalAction.WAIT,
            public_reason="First model decision",
            confidence=0.8,
        )
    )
    runtime = BudgetedAgentProvider(
        provider,
        AgentProviderLimits(max_calls=1, max_calls_per_agent=5),
    )
    first = runtime.decide(provider_test_observation())
    second = runtime.decide(provider_test_observation().model_copy(
        update={"current_minute": 1325}
    ))

    assert first.generated_by_ai is True
    assert second.generated_by_ai is False
    assert second.failure_kind == "budget_exhausted"
    assert len(provider.observations) == 1
    assert runtime.usage().budget_exhaustions == 1


def test_rejected_generative_action_cannot_disable_protected_storage():
    malicious = ScriptedProvider(
        AgentProposal(
            action=AgentProposalAction.OPERATE_EQUIPMENT,
            target_id="cold_storage",
            public_reason="Attempt the protected load for a safety test.",
            confidence=0.9,
        )
    )
    runtime = BudgetedAgentProvider(
        malicious,
        AgentProviderLimits(
            max_calls=40,
            max_calls_per_agent=10,
            token_budget=50_000,
            cost_budget_usd=10,
        ),
    )
    run = GameMaster(
        build_demo_store(),
        get_scenario("green-close"),
        42,
        agent_provider=runtime,
    ).run()

    cold_storage = next(item for item in run.store.equipment if item.id == "cold_storage")
    assert str(cold_storage.state) == "on"
    assert any(
        decision.proposal.target_id == "cold_storage"
        and decision.generated_by_ai
        and not decision.accepted
        for decision in run.agent_decisions
    )
    assert not any(
        event.target_id == "cold_storage" and event.type == "equipment_state_changed"
        for event in run.events
    )


def test_api_and_persisted_runs_never_expose_backend_secret(monkeypatch, tmp_path):
    secret = "sk-test-super-secret-never-persist"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    repository = SQLiteRepository(tmp_path / "agent-secrets.sqlite3")
    app.state.repository = repository
    scripted = ScriptedProvider(
        AgentProposal(
            action=AgentProposalAction.WAIT,
            public_reason="Use a safe mocked provider response.",
            confidence=0.8,
        )
    )
    monkeypatch.setattr(
        "app.projects.api.build_agent_provider",
        lambda mode, model, timeout_seconds: scripted,
    )

    with TestClient(app) as client:
        status_payload = client.get("/api/ai/status").json()
        project = client.post("/api/demo/bootstrap").json()["project"]
        run_payload = client.post(
            f"/api/projects/{project['id']}/runs",
            json={
                "mode": "openai",
                "model": "configured-model",
                "seed": 19,
                "sample_count": 25,
                "max_calls": 4,
                "max_calls_per_agent": 2,
            },
        ).json()

    persisted = repository.get_simulation_run(project["id"], run_payload["id"])
    combined = json.dumps(
        {
            "status": status_payload,
            "response": run_payload,
            "persisted": persisted.model_dump(mode="json") if persisted else None,
        }
    )
    assert secret not in combined
    assert status_payload["credentials_exposed"] is False
    assert run_payload["agent_mode"] == "openai"
    assert run_payload["agent_provider"] == "mock-openai"


def test_ai_connection_endpoint_is_non_blocking_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with TestClient(app) as client:
        deterministic = client.post(
            "/api/ai/test",
            json={"mode": "deterministic"},
        )
        unavailable = client.post(
            "/api/ai/test",
            json={"mode": "openai"},
        )
    assert deterministic.status_code == 200
    assert deterministic.json()["success"] is True
    assert unavailable.status_code == 200
    assert unavailable.json()["success"] is False
