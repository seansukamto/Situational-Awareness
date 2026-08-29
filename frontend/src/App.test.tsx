// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { DemoBundle, PersistedSimulationRun, SimulationRunSummary } from "./types";

const demo: DemoBundle = {
  project: {
    id: "project_demo",
    name: "Demo store",
    created_at: "2026-08-29T08:00:00Z",
    updated_at: "2026-08-29T08:00:00Z",
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
    failure_message: run.failure_message,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("application startup", () => {
  it("loads run history without generating simulations or analyses", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/demo/bootstrap")) {
        return new Response(JSON.stringify(demo), {
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

    expect(await screen.findByRole("heading", { name: "No simulation runs yet" })).toBeVisible();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const requests = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      method: init?.method ?? "GET",
    }));
    expect(requests[0].url.endsWith("/api/demo/bootstrap")).toBe(true);
    expect(requests[0].method).toBe("POST");
    expect(requests[1].url.endsWith("/api/projects/project_demo/runs")).toBe(true);
    expect(requests[1].method).toBe("GET");
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
