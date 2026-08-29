from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from threading import BoundedSemaphore
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import ValidationError

from .models import (
    AGENT_PROMPT_TEMPLATE_VERSION,
    AIStatusResponse,
    AgentDecisionResult,
    AgentMode,
    AgentObservation,
    AgentProposal,
    AgentProviderLimits,
    AgentProviderResponse,
    AgentUsageSummary,
    ProviderModeStatus,
)
from .schema import openai_strict_json_schema


PROVIDER_INSTRUCTIONS = """You propose one bounded retail-store action for the observed agent.
Return only the structured public proposal. Never provide hidden reasoning or chain-of-thought.
Use public_reason for a short audit-ready rationale. The Game Master will independently validate
the proposal and is the only authority allowed to change simulation state or calculate impacts."""


class ProviderUnavailable(RuntimeError):
    pass


class AgentProvider(ABC):
    mode: AgentMode
    name: str
    model: str
    configuration_fingerprint: str

    @abstractmethod
    def propose(self, observation: AgentObservation) -> AgentProviderResponse:
        raise NotImplementedError


def _fingerprint(payload: dict[str, str | float | bool | None]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _safe_base_url(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


class DeterministicAgentProvider(AgentProvider):
    mode = AgentMode.DETERMINISTIC
    name = "deterministic"
    model = "situational-awareness-rules"
    configuration_fingerprint = _fingerprint(
        {"provider": name, "model": model, "prompt": AGENT_PROMPT_TEMPLATE_VERSION}
    )

    def propose(self, observation: AgentObservation) -> AgentProviderResponse:
        return AgentProviderResponse(proposal=observation.deterministic_fallback)


class OpenAIAgentProvider(AgentProvider):
    mode = AgentMode.OPENAI
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client=None,
        input_cost_per_million_usd: float = 0,
        output_cost_per_million_usd: float = 0,
    ):
        if not api_key:
            raise ProviderUnavailable("OpenAI is not configured on the backend")
        if not model:
            raise ProviderUnavailable("OPENAI_MODEL is not configured on the backend")
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self.client = client
        self.model = model
        self.input_cost_per_million_usd = max(0, input_cost_per_million_usd)
        self.output_cost_per_million_usd = max(0, output_cost_per_million_usd)
        self.configuration_fingerprint = _fingerprint(
            {
                "provider": self.name,
                "model": model,
                "prompt": AGENT_PROMPT_TEMPLATE_VERSION,
                "sdk": "official-openai-responses",
            }
        )

    def propose(self, observation: AgentObservation) -> AgentProviderResponse:
        response = self.client.responses.create(
            model=self.model,
            instructions=PROVIDER_INSTRUCTIONS,
            input=observation.model_dump_json(exclude_none=True),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "retail_agent_proposal",
                    "strict": True,
                    "schema": openai_strict_json_schema(AgentProposal),
                }
            },
            max_output_tokens=180,
            store=False,
        )
        proposal = AgentProposal.model_validate_json(response.output_text)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        estimated_cost = (
            input_tokens * self.input_cost_per_million_usd
            + output_tokens * self.output_cost_per_million_usd
        ) / 1_000_000
        return AgentProviderResponse(
            proposal=proposal,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
        )


class OllamaAgentProvider(AgentProvider):
    mode = AgentMode.OLLAMA
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ProviderUnavailable("OLLAMA_BASE_URL is not configured on the backend")
        if not model:
            raise ProviderUnavailable("OLLAMA_MODEL is not configured on the backend")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self.configuration_fingerprint = _fingerprint(
            {
                "provider": self.name,
                "model": model,
                "base_url": _safe_base_url(base_url),
                "prompt": AGENT_PROMPT_TEMPLATE_VERSION,
            }
        )

    def propose(self, observation: AgentObservation) -> AgentProviderResponse:
        response = self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": AgentProposal.model_json_schema(),
                "messages": [
                    {"role": "system", "content": PROVIDER_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": observation.model_dump_json(exclude_none=True),
                    },
                ],
                "options": {"temperature": 0.2},
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("message", {}).get("content", "")
        proposal = AgentProposal.model_validate_json(content)
        return AgentProviderResponse(
            proposal=proposal,
            input_tokens=int(payload.get("prompt_eval_count", 0) or 0),
            output_tokens=int(payload.get("eval_count", 0) or 0),
            estimated_cost_usd=0,
        )


class UnavailableAgentProvider(AgentProvider):
    def __init__(self, mode: AgentMode, model: str, reason: str):
        self.mode = mode
        self.name = str(mode)
        self.model = model or "not-configured"
        self.reason = reason
        self.configuration_fingerprint = _fingerprint(
            {"provider": self.name, "model": self.model, "configured": False}
        )

    def propose(self, observation: AgentObservation) -> AgentProviderResponse:
        raise ProviderUnavailable(self.reason)


def _failure_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout", "The selected agent provider timed out"
    if isinstance(exc, ProviderUnavailable):
        return "unavailable", str(exc)
    if isinstance(exc, (ValidationError, json.JSONDecodeError, ValueError, TypeError)):
        return "invalid_output", "The provider returned an invalid structured proposal"
    return "provider_error", "The selected agent provider could not produce a proposal"


class BudgetedAgentProvider:
    """Adds validation, budgets, caching, and explicit deterministic fallback."""

    def __init__(self, provider: AgentProvider, limits: AgentProviderLimits):
        self.provider = provider
        self.limits = limits
        self.fallback = DeterministicAgentProvider()
        self._calls_per_agent: dict[str, int] = defaultdict(int)
        self._cache: dict[str, AgentProviderResponse] = {}
        self._usage = AgentUsageSummary()
        self._semaphore = BoundedSemaphore(limits.max_concurrency)

    @property
    def mode(self) -> AgentMode:
        return self.provider.mode

    @property
    def name(self) -> str:
        return self.provider.name

    @property
    def model(self) -> str:
        return self.provider.model

    @property
    def configuration_fingerprint(self) -> str:
        return self.provider.configuration_fingerprint

    def usage(self) -> AgentUsageSummary:
        return self._usage.model_copy(deep=True)

    def decide(
        self,
        observation: AgentObservation,
        *,
        allow_external: bool = True,
    ) -> AgentDecisionResult:
        if self.mode == AgentMode.DETERMINISTIC or not allow_external:
            self._usage.deterministic_decisions += 1
            return AgentDecisionResult(
                proposal=self.fallback.propose(observation).proposal,
                provider="deterministic",
                model=self.fallback.model,
                generated_by_ai=False,
            )

        exhausted = self._budget_failure(observation.agent_id)
        if exhausted:
            self._usage.budget_exhaustions += 1
            self._usage.fallback_decisions += 1
            self._usage.deterministic_decisions += 1
            return AgentDecisionResult(
                proposal=self.fallback.propose(observation).proposal,
                provider="deterministic",
                model=self.fallback.model,
                generated_by_ai=False,
                fallback_used=True,
                failure_kind="budget_exhausted",
                failure_message=exhausted,
            )

        cache_key = hashlib.sha256(observation.cache_key_payload().encode()).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._usage.cached_decisions += 1
            return AgentDecisionResult(
                proposal=cached.proposal,
                provider=self.provider.name,
                model=self.provider.model,
                generated_by_ai=True,
                cache_hit=True,
            )

        self._usage.provider_calls += 1
        self._calls_per_agent[observation.agent_id] += 1
        started = time.perf_counter()
        try:
            with self._semaphore:
                raw = self.provider.propose(observation)
            response = AgentProviderResponse.model_validate(raw)
            latency_ms = (time.perf_counter() - started) * 1_000
            self._cache[cache_key] = response
            self._usage.input_tokens += response.input_tokens
            self._usage.output_tokens += response.output_tokens
            self._usage.estimated_cost_usd += response.estimated_cost_usd
            self._usage.total_latency_ms += latency_ms
            return AgentDecisionResult(
                proposal=response.proposal,
                provider=self.provider.name,
                model=self.provider.model,
                generated_by_ai=True,
                latency_ms=round(latency_ms, 3),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                estimated_cost_usd=response.estimated_cost_usd,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1_000
            failure_kind, failure_message = _failure_details(exc)
            self._usage.provider_failures += 1
            self._usage.fallback_decisions += 1
            self._usage.deterministic_decisions += 1
            self._usage.total_latency_ms += latency_ms
            return AgentDecisionResult(
                proposal=self.fallback.propose(observation).proposal,
                provider="deterministic",
                model=self.fallback.model,
                generated_by_ai=False,
                fallback_used=True,
                failure_kind=failure_kind,
                failure_message=failure_message,
                latency_ms=round(latency_ms, 3),
            )

    def _budget_failure(self, agent_id: str) -> str | None:
        if self._usage.provider_calls >= self.limits.max_calls:
            return "Maximum provider calls for this scenario were reached"
        if self._calls_per_agent[agent_id] >= self.limits.max_calls_per_agent:
            return "Maximum provider calls for this agent were reached"
        if self._usage.total_tokens >= self.limits.token_budget:
            return "The provider token budget was exhausted"
        if self._usage.estimated_cost_usd >= self.limits.cost_budget_usd:
            return "The estimated provider cost budget was exhausted"
        return None


def _configured_model(mode: AgentMode) -> str:
    if mode == AgentMode.OPENAI:
        return os.getenv("OPENAI_MODEL", "")
    if mode == AgentMode.OLLAMA:
        return os.getenv("OLLAMA_MODEL", "")
    return DeterministicAgentProvider.model


def build_agent_provider(
    mode: AgentMode,
    *,
    model: str | None,
    timeout_seconds: float,
) -> AgentProvider:
    if mode == AgentMode.DETERMINISTIC:
        return DeterministicAgentProvider()
    configured_model = _configured_model(mode)
    selected_model = model or configured_model
    if not configured_model:
        variable = "OPENAI_MODEL" if mode == AgentMode.OPENAI else "OLLAMA_MODEL"
        return UnavailableAgentProvider(
            mode,
            selected_model,
            f"{variable} is not configured on the backend",
        )
    if model and model != configured_model:
        return UnavailableAgentProvider(
            mode,
            selected_model,
            "The requested model is not in the backend allow-list",
        )
    if mode == AgentMode.OPENAI:
        api_key = os.getenv("OPENAI_API_KEY", "")
        try:
            return OpenAIAgentProvider(
                api_key=api_key,
                model=selected_model,
                timeout_seconds=timeout_seconds,
                input_cost_per_million_usd=float(
                    os.getenv("OPENAI_INPUT_COST_PER_1M_USD", "0")
                ),
                output_cost_per_million_usd=float(
                    os.getenv("OPENAI_OUTPUT_COST_PER_1M_USD", "0")
                ),
            )
        except ProviderUnavailable as exc:
            return UnavailableAgentProvider(mode, selected_model, str(exc))
        except Exception:
            return UnavailableAgentProvider(
                mode,
                selected_model,
                "The OpenAI provider could not be initialized on the backend",
            )
    base_url = os.getenv("OLLAMA_BASE_URL", "")
    try:
        return OllamaAgentProvider(
            base_url=base_url,
            model=selected_model,
            timeout_seconds=timeout_seconds,
        )
    except ProviderUnavailable as exc:
        return UnavailableAgentProvider(mode, selected_model, str(exc))
    except Exception:
        return UnavailableAgentProvider(
            mode,
            selected_model,
            "The Ollama provider could not be initialized on the backend",
        )


def configured_provider_status(*, check_ollama: bool = True) -> AIStatusResponse:
    openai_model = os.getenv("OPENAI_MODEL", "")
    openai_configured = bool(os.getenv("OPENAI_API_KEY") and openai_model)
    ollama_url = os.getenv("OLLAMA_BASE_URL", "")
    ollama_model = os.getenv("OLLAMA_MODEL", "")
    ollama_configured = bool(ollama_url and ollama_model)
    ollama_available = False
    ollama_detail = "Configure OLLAMA_BASE_URL and OLLAMA_MODEL on the backend"
    if ollama_configured:
        ollama_detail = "Configured; connection has not been tested"
        if check_ollama:
            try:
                response = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=0.6)
                response.raise_for_status()
                ollama_available = True
                ollama_detail = "Connected to the configured local endpoint"
            except Exception:
                ollama_detail = "Configured, but the local endpoint is unavailable"
    return AIStatusResponse(
        modes=[
            ProviderModeStatus(
                mode=AgentMode.DETERMINISTIC,
                provider="deterministic",
                available=True,
                configured=True,
                model=DeterministicAgentProvider.model,
                detail="Always available; reproducible and requires no credentials",
            ),
            ProviderModeStatus(
                mode=AgentMode.OPENAI,
                provider="openai",
                available=openai_configured,
                configured=openai_configured,
                model=openai_model or None,
                detail=(
                    "Configured through backend environment variables"
                    if openai_configured
                    else "Configure OPENAI_API_KEY and OPENAI_MODEL on the backend"
                ),
            ),
            ProviderModeStatus(
                mode=AgentMode.OLLAMA,
                provider="ollama",
                available=ollama_available,
                configured=ollama_configured,
                model=ollama_model or None,
                detail=ollama_detail,
            ),
        ]
    )
