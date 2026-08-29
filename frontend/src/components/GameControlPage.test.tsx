// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GameControlPage } from "./GameControlPage";
import type { Project } from "../types";


const project = {
  id: "project_demo",
  name: "Demo store",
  created_at: "2026-08-30T00:00:00Z",
  updated_at: "2026-08-30T00:00:00Z",
  agent_settings: {
    mode: "deterministic" as const,
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
    name: "Demo store",
    timezone: "Asia/Singapore",
    floor_area_m2: 180,
    opening_minute: 600,
    closing_minute: 1320,
    zones: [{ id: "sales", label: "Sales floor", center: { x: 0, z: 0 }, width: 8, depth: 6 }],
    equipment: [{
      id: "display_lights",
      label: "Display lights",
      zone_id: "sales",
      position: { x: 1, z: 1 },
      state: "on",
      power_kw_by_state: { on: 2, standby: 0.2, off: 0 },
      criticality: "non_critical",
      customer_facing: true,
      switchable_by_roles: ["closing_associate", "manager"],
    }],
    agents: [],
    customers: [],
    tariff_sgd_per_kwh: 0.3,
    grid_emission_factor_kg_per_kwh: 0.4,
  },
} satisfies Project;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GameControlPage", () => {
  it("creates non-energy habits with a safe zone target", async () => {
    const templates: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/projects/project_demo/task-templates") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        templates.push({
          ...body,
          id: "template_waste",
          project_id: project.id,
          active: true,
          created_at: "2026-08-30T00:00:00Z",
          updated_at: "2026-08-30T00:00:00Z",
        });
        return Response.json(templates[0], { status: 201 });
      }
      if (url.endsWith("/api/projects/project_demo/task-templates")) return Response.json(templates);
      if (
        url.endsWith("/api/projects/project_demo/game-days")
        || url.endsWith("/api/projects/project_demo/staff")
        || url.endsWith("/api/projects/project_demo/game-policies")
      ) return Response.json([]);
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(<QueryClientProvider client={client}><GameControlPage project={project} /></QueryClientProvider>);

    fireEvent.click(await screen.findByRole("button", { name: "＋ New task" }));
    fireEvent.change(screen.getByLabelText("Task name"), { target: { value: "Sort reusable packaging" } });
    fireEvent.change(screen.getByLabelText("Staff instruction"), { target: { value: "Separate reusable packaging from general waste." } });
    fireEvent.change(screen.getByLabelText("Why this is sustainable"), { target: { value: "Divert clean packaging for reuse instead of disposal." } });
    fireEvent.change(screen.getByLabelText("Outcome metric"), { target: { value: "kg diverted from general waste" } });
    fireEvent.change(screen.getByLabelText("Estimated impact (optional)"), { target: { value: "2.5" } });
    fireEvent.change(screen.getByLabelText("Impact unit"), { target: { value: "kg" } });
    fireEvent.change(screen.getByLabelText("Sustainability domain"), { target: { value: "waste" } });
    fireEvent.change(screen.getByLabelText("Safe task target"), { target: { value: "zone:sales" } });
    fireEvent.click(screen.getByRole("button", { name: "Add challenge" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => (
      String(input).endsWith("/task-templates") && init?.method === "POST"
    ))).toBe(true));
    const createCall = fetchMock.mock.calls.find(([input, init]) => (
      String(input).endsWith("/task-templates") && init?.method === "POST"
    ));
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      domain: "waste",
      zone_id: "sales",
      equipment_id: null,
      allowed_roles: ["manager", "closing_associate", "cashier"],
      sustainability_mechanism: "Divert clean packaging for reuse instead of disposal.",
      impact_metric: "kg diverted from general waste",
      estimated_impact_value: 2.5,
      estimated_impact_unit: "kg",
    });
  });
});
