// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentIntelligenceSettings, SimulationRunSummary } from "../types";
import { RunHistory } from "./RunHistory";

afterEach(() => cleanup());

const agentSettings: AgentIntelligenceSettings = {
  mode: "deterministic",
  model: null,
  max_calls: 12,
  max_calls_per_agent: 3,
  timeout_seconds: 5,
  max_concurrency: 1,
  token_budget: 6000,
  cost_budget_usd: 0.25,
};

function summary(overrides: Partial<SimulationRunSummary> = {}): SimulationRunSummary {
  return {
    id: "run_abcdef123456",
    project_id: "project_1",
    created_at: "2026-08-29T08:00:00Z",
    completed_at: "2026-08-29T08:00:05Z",
    status: "completed",
    seed: 42,
    sample_count: 120,
    estimated_savings_sgd: 81.4,
    configuration_current: true,
    game_master_rules_version: "rules-v1",
    agent_mode: "deterministic",
    agent_provider: "deterministic",
    agent_model: "rules-v1",
    fallback_decisions: 0,
    provider_calls: 0,
    total_tokens: 0,
    estimated_cost_usd: 0,
    failure_message: null,
    ...overrides,
  };
}

describe("RunHistory", () => {
  it("shows the polished empty state without creating a run", () => {
    const onCreate = vi.fn();
    render(
      <RunHistory
        runs={[]}
        selectedRunId={null}
        loading={false}
        creating={false}
        defaultAgentSettings={agentSettings}
        onSelect={vi.fn()}
        onCreate={onCreate}
      />,
    );

    expect(screen.getByText("No simulation runs yet")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Run simulation/i })).toBeTruthy();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("creates one paired comparison from the run dialog", () => {
    const onCreate = vi.fn();
    render(
      <RunHistory
        runs={[]}
        selectedRunId={null}
        loading={false}
        creating={false}
        defaultAgentSettings={agentSettings}
        onSelect={vi.fn()}
        onCreate={onCreate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Run simulation/i }));
    expect(screen.getByText("One run record")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Replay seed"), { target: { value: "91" } });
    fireEvent.change(screen.getByLabelText("Monte Carlo samples"), { target: { value: "60" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Run simulation" }));
    expect(onCreate).toHaveBeenCalledWith({ seed: 91, sample_count: 60, ...agentSettings });
  });

  it("shows history metadata and selects an older immutable run", () => {
    const onSelect = vi.fn();
    const latest = summary({ configuration_current: false });
    const older = summary({
      id: "run_9876543210ab",
      created_at: "2026-08-28T08:00:00Z",
      seed: 173,
      sample_count: 25,
      estimated_savings_sgd: 44,
    });
    render(
      <RunHistory
        runs={[latest, older]}
        selectedRunId={latest.id}
        loading={false}
        creating={false}
        defaultAgentSettings={agentSettings}
        onSelect={onSelect}
        onCreate={vi.fn()}
      />,
    );

    expect(screen.getByText("Configuration changed since latest run")).toBeTruthy();
    expect(screen.getAllByText("Configuration outdated")).toHaveLength(1);
    expect(screen.getByText("98765432")).toBeTruthy();
    fireEvent.click(screen.getByText("98765432").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith(older.id);
  });
});
