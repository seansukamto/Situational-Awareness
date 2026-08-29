// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AIStatus, Project } from "../types";
import { AgentIntelligence } from "./AgentIntelligence";

const project = {
  id: "project_demo",
  name: "Demo",
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
  agent_settings: {
    mode: "deterministic",
    model: null,
    max_calls: 12,
    max_calls_per_agent: 3,
    timeout_seconds: 5,
    max_concurrency: 1,
    token_budget: 6000,
    cost_budget_usd: 0.25,
  },
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
    name: "Demo",
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
} satisfies Project;

const status: AIStatus = {
  selected_mode: "deterministic",
  prompt_template_version: "test-prompt-v1",
  credentials_exposed: false,
  modes: [
    { mode: "deterministic", provider: "deterministic", available: true, configured: true, model: "rules-v1", detail: "Always available without credentials." },
    { mode: "openai", provider: "openai", available: false, configured: false, model: null, detail: "Set backend environment variables." },
    { mode: "ollama", provider: "ollama", available: false, configured: false, model: null, detail: "Local endpoint is not configured." },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentIntelligence", () => {
  it("keeps deterministic mode available and makes missing providers clear", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      success: true,
      mode: "deterministic",
      provider: "deterministic",
      model: "rules-v1",
      latency_ms: 0,
      proposal: { action: "wait", target_id: null, destination: null, public_reason: "Safe deterministic test.", confidence: 1 },
      error: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <AgentIntelligence project={project} status={status} statusLoading={false} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: /Deterministic/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /OpenAI/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Local Ollama/i })).toBeDisabled();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("Connection verified")).toBeVisible();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/ai/test");
    expect(String(fetchMock.mock.calls[0][1]?.body)).not.toContain("API_KEY");
  });
});
