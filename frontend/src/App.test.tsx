// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { AIStatus, DemoBundle, PersistedSimulationRun, SimulationRunSummary } from "./types";

const agentSettings = {
  mode: "deterministic" as const,
  model: null,
  max_calls: 12,
  max_calls_per_agent: 3,
  timeout_seconds: 5,
  max_concurrency: 1,
  token_budget: 6000,
  cost_budget_usd: 0.25,
};

const aiStatus: AIStatus = {
  selected_mode: "deterministic",
  prompt_template_version: "test-prompt-v1",
  credentials_exposed: false,
  modes: [
    { mode: "deterministic", provider: "deterministic", available: true, configured: true, model: "rules-v1", detail: "Always available" },
    { mode: "openai", provider: "openai", available: false, configured: false, model: null, detail: "Not configured" },
    { mode: "ollama", provider: "ollama", available: false, configured: false, model: null, detail: "Not configured" },
  ],
};

const demo: DemoBundle = {
  project: {
    id: "project_demo",
    name: "Demo store",
    created_at: "2026-08-29T08:00:00Z",
    updated_at: "2026-08-29T08:00:00Z",
    agent_settings: agentSettings,
    settings: {
      scenario_id: "green-close",
      operating_days_per_year: 360,
      labour_cost_sgd_per_hour: 18,
      annual_revenue_sgd: 1_000_000,
      equipment_load_uncertainty_pct: 10,
      tariff_uncertainty_pct: 5,
      adoption_rate: 0.8,
    },
    store: {
      id: "store_demo",
      name: "Demo store",
      timezone: "Asia/Singapore",
      floor_area_m2: 180,
      opening_minute: 600,
      closing_minute: 1320,
      zones: [],
      equipment: [],
      agents: [],
      customers: [],
      tariff_sgd_per_kwh: 0.3,
      grid_emission_factor_kg_per_kwh: 0.4,
    },
  },
  bills: [],
};

function pendingRun(id: string, seed: number): PersistedSimulationRun {
  return {
    id,
    project_id: demo.project.id,
    created_at: "2026-08-29T08:00:00Z",
    completed_at: null,
    status: "running",
    seed,
    sample_count: 25,
    comparison: null,
    impact_analysis: null,
    store_snapshot: demo.project.store,
    scenario_settings_snapshot: demo.project.settings,
    evidence_snapshot: null,
    baseline_explanations: [],
    intervention_explanations: [],
    configuration_hash: "snapshot-hash",
    configuration_current: true,
    game_master_rules_version: "test-rules-v1",
    game_master_rules_snapshot: [],
    agent_mode: "deterministic",
    agent_provider: "deterministic",
    agent_model: "rules-v1",
    provider_configuration_fingerprint: "deterministic:rules-v1",
    prompt_template_version: "test-prompt-v1",
    agent_settings_snapshot: agentSettings,
    agent_usage: {
      provider_calls: 0,
      deterministic_decisions: 0,
      cached_decisions: 0,
      fallback_decisions: 0,
      provider_failures: 0,
      budget_exhaustions: 0,
      input_tokens: 0,
      output_tokens: 0,
      estimated_cost_usd: 0,
      total_latency_ms: 0,
    },
    failure_message: null,
  };
}

function runSummary(run: PersistedSimulationRun): SimulationRunSummary {
  return {
    id: run.id,
    project_id: run.project_id,
    created_at: run.created_at,
    completed_at: run.completed_at,
    status: run.status,
    seed: run.seed,
    sample_count: run.sample_count,
    estimated_savings_sgd: null,
    configuration_current: run.configuration_current,
    game_master_rules_version: run.game_master_rules_version,
    agent_mode: run.agent_mode,
    agent_provider: run.agent_provider,
    agent_model: run.agent_model,
    fallback_decisions: run.agent_usage.fallback_decisions,
    provider_calls: run.agent_usage.provider_calls,
    total_tokens: run.agent_usage.input_tokens + run.agent_usage.output_tokens,
    estimated_cost_usd: run.agent_usage.estimated_cost_usd,
    failure_message: run.failure_message,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("application startup", () => {
  it("opens the live staff game without generating simulations or analyses", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/demo/bootstrap")) {
        return new Response(JSON.stringify(demo), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/ai/status")) {
        return new Response(JSON.stringify(aiStatus), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/projects/project_demo/runs") && !init?.method) {
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (
        url.endsWith("/api/projects/project_demo/game-days")
        || url.endsWith("/api/projects/project_demo/task-templates")
        || url.endsWith("/api/projects/project_demo/staff")
      ) {
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Run today’s sustainability game." })).toBeVisible();
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).endsWith("/api/projects/project_demo/staff")
    ))).toBe(true));

    const requests = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      method: init?.method ?? "GET",
    }));
    expect(requests[0].url.endsWith("/api/demo/bootstrap")).toBe(true);
    expect(requests[0].method).toBe("POST");
    expect(requests.some(({ url, method }) => url.endsWith("/api/ai/status") && method === "GET")).toBe(true);
    expect(requests.some(({ url, method }) => url.endsWith("/api/projects/project_demo/runs") && method === "GET")).toBe(true);
    expect(requests.some(({ url }) => url.includes("/simulations/") || url.includes("/analysis"))).toBe(false);
    expect(requests.some(({ url, method }) => url.endsWith("/runs") && method === "POST")).toBe(false);
  });

  it("keeps a newly created run selected while stale history refreshes", async () => {
    const oldRun = pendingRun("run_old00001", 11);
    const newRun = pendingRun("run_new00002", 22);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/demo/bootstrap")) {
        return new Response(JSON.stringify(demo), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/ai/status")) {
        return new Response(JSON.stringify(aiStatus), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/projects/project_demo/runs") && init?.method === "POST") {
        return new Response(JSON.stringify(newRun), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/projects/project_demo/runs")) {
        return new Response(JSON.stringify([runSummary(oldRun)]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/projects/project_demo/runs/run_old00001")) {
        return new Response(JSON.stringify(oldRun), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (
        url.endsWith("/api/projects/project_demo/game-days")
        || url.endsWith("/api/projects/project_demo/task-templates")
        || url.endsWith("/api/projects/project_demo/staff")
      ) {
        return new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Run today’s sustainability game." })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Simulation" }));
    expect(await screen.findByRole("heading", { name: "Run OLD00001" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Run new simulation/i }));
    const dialog = await screen.findByRole("dialog", { name: "Run simulation" });
    fireEvent.click(dialog.querySelector<HTMLButtonElement>('button[type="submit"]')!);

    expect(await screen.findByRole("heading", { name: "Run NEW00002" })).toBeVisible();
    expect(fetchMock.mock.calls.filter(([input, init]) => (
      String(input).endsWith("/runs") && init?.method === "POST"
    ))).toHaveLength(1);
  });
});
