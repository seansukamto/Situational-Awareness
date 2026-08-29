from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AGENT_PROMPT_TEMPLATE_VERSION = "retail-agent-proposal-2026.08"


class AgentMode(StrEnum):
    DETERMINISTIC = "deterministic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class AgentProposalAction(StrEnum):
    MOVE = "move"
    OPERATE_EQUIPMENT = "operate_equipment"
    ASSIST_CUSTOMER = "assist_customer"
    REMIND_STAFF = "remind_staff"
    WAIT = "wait"
    EXIT = "exit"


class AgentProposal(BaseModel):
    """The complete public action surface available to any agent provider."""

    model_config = ConfigDict(extra="forbid")

    action: AgentProposalAction
    target_id: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    public_reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def required_action_fields(self):
        if self.action == AgentProposalAction.OPERATE_EQUIPMENT and not self.target_id:
            raise ValueError("operate_equipment requires target_id")
        if self.action == AgentProposalAction.MOVE and not self.destination:
            raise ValueError("move requires destination")
        return self


class AgentObservation(BaseModel):
    """A deliberately bounded, non-sensitive view of one decision point."""

    model_config = ConfigDict(extra="forbid")

    current_minute: int
    scenario_id: str
    actor_kind: Literal["staff", "consumer"]
    agent_id: str
    agent_label: str
    role_or_segment: str
    zone_id: str
    zone_state: dict[str, Any]
    nearby_agents: list[dict[str, Any]] = Field(max_length=8)
    nearby_equipment: list[dict[str, Any]] = Field(max_length=8)
    customer_count: int = Field(ge=0)
    permitted_actions: list[AgentProposalAction] = Field(max_length=6)
    permitted_target_ids: list[str] = Field(default_factory=list, max_length=16)
    traits: dict[str, float]
    operating_state: dict[str, float | bool | str]
    recent_memories: list[str] = Field(default_factory=list, max_length=4)
    memory_summary: str = Field(default="", max_length=480)
    sustainability_intervention: dict[str, Any]
    game_master_constraints: list[str] = Field(max_length=8)
    deterministic_fallback: AgentProposal

    def cache_key_payload(self) -> str:
        return self.model_dump_json(exclude_none=True)

    def audit_summary(self) -> dict[str, Any]:
        return {
            "actor_kind": self.actor_kind,
            "zone_id": self.zone_id,
            "customer_count": self.customer_count,
            "permitted_actions": [str(action) for action in self.permitted_actions],
            "permitted_target_ids": self.permitted_target_ids,
            "recent_memory_count": len(self.recent_memories),
            "memory_summary": self.memory_summary,
        }


class AgentProviderLimits(BaseModel):
    max_calls: int = Field(default=12, ge=0, le=200)
    max_calls_per_agent: int = Field(default=3, ge=0, le=50)
    timeout_seconds: float = Field(default=5, ge=0.25, le=60)
    max_concurrency: int = Field(default=1, ge=1, le=8)
    token_budget: int = Field(default=6_000, ge=0, le=1_000_000)
    cost_budget_usd: float = Field(default=0.25, ge=0, le=1_000)


class AgentIntelligenceSettings(AgentProviderLimits):
    mode: AgentMode = AgentMode.DETERMINISTIC
    model: str | None = Field(default=None, max_length=120)


class AgentProviderResponse(BaseModel):
    proposal: AgentProposal
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)


class AgentDecisionResult(BaseModel):
    proposal: AgentProposal
    provider: str
    model: str
    generated_by_ai: bool
    fallback_used: bool = False
    failure_kind: str | None = None
    failure_message: str | None = None
    cache_hit: bool = False
    latency_ms: float = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)


class AgentDecisionAudit(BaseModel):
    event_seq: int | None = None
    at_minute: int
    scenario_id: str
    actor_kind: Literal["staff", "consumer"]
    agent_id: str
    observation: dict[str, Any]
    proposal: AgentProposal
    accepted: bool
    outcome: str
    provider: str
    model: str
    generated_by_ai: bool
    fallback_used: bool = False
    failure_kind: str | None = None
    public_reason: str
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0
    memory_summary: str = ""


class AgentUsageSummary(BaseModel):
    provider_calls: int = 0
    deterministic_decisions: int = 0
    cached_decisions: int = 0
    fallback_decisions: int = 0
    provider_failures: int = 0
    budget_exhaustions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0
    total_latency_ms: float = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def plus(self, other: "AgentUsageSummary") -> "AgentUsageSummary":
        return AgentUsageSummary(
            provider_calls=self.provider_calls + other.provider_calls,
            deterministic_decisions=(
                self.deterministic_decisions + other.deterministic_decisions
            ),
            cached_decisions=self.cached_decisions + other.cached_decisions,
            fallback_decisions=self.fallback_decisions + other.fallback_decisions,
            provider_failures=self.provider_failures + other.provider_failures,
            budget_exhaustions=self.budget_exhaustions + other.budget_exhaustions,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            estimated_cost_usd=round(
                self.estimated_cost_usd + other.estimated_cost_usd,
                8,
            ),
            total_latency_ms=round(
                self.total_latency_ms + other.total_latency_ms,
                3,
            ),
        )


class ProviderModeStatus(BaseModel):
    mode: AgentMode
    provider: str
    available: bool
    configured: bool
    model: str | None = None
    detail: str


class AIStatusResponse(BaseModel):
    modes: list[ProviderModeStatus]
    selected_mode: AgentMode = AgentMode.DETERMINISTIC
    prompt_template_version: str = AGENT_PROMPT_TEMPLATE_VERSION
    credentials_exposed: Literal[False] = False


class AITestRequest(BaseModel):
    mode: AgentMode
    model: str | None = Field(default=None, max_length=120)
    timeout_seconds: float = Field(default=5, ge=0.25, le=60)


class AITestResponse(BaseModel):
    success: bool
    mode: AgentMode
    provider: str
    model: str
    latency_ms: float
    proposal: AgentProposal | None = None
    error: str | None = None
