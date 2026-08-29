// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StaffConfigurationPage } from "./StaffConfigurationPage";
import { StaffGamePage } from "./StaffGamePage";
import type { GameDay, Project, StaffProfile, TaskInstance } from "../types";


const project: Project = {
  id: "project_demo",
  name: "Demo store",
  created_at: "2026-08-29T08:00:00Z",
  updated_at: "2026-08-29T08:00:00Z",
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
};

const staff: StaffProfile = {
  id: "staff_ava",
  project_id: project.id,
  display_name: "Ava",
  normalized_name: "ava",
  role: "closing_associate",
  avatar_id: "associate",
  authorized_zone_ids: ["sales"],
  authorized_equipment_ids: ["display_lights"],
  default_shift_start: 600,
  default_shift_end: 1320,
  active: true,
  created_at: "2026-08-29T08:00:00Z",
  updated_at: "2026-08-29T08:00:00Z",
};

const gameDay: GameDay = {
  id: "game_today",
  project_id: project.id,
  local_date: "2026-08-29",
  timezone: "Asia/Singapore",
  start_minute: 600,
  end_minute: 1320,
  status: "active",
  join_token: "join-token",
  policy_version: "policy-v1",
  scoring_version: "score-v1",
  created_at: "2026-08-29T08:00:00Z",
  started_at: "2026-08-29T08:01:00Z",
  completed_at: null,
};

const task: TaskInstance = {
  id: "task_lights",
  game_day_id: gameDay.id,
  project_id: project.id,
  template_id: "template_lights",
  label: "Switch off unused display lights",
  description: "Confirm the quiet display is no longer needed, then switch it off.",
  domain: "energy",
  zone_id: "sales",
  equipment_id: "display_lights",
  allowed_roles: ["closing_associate"],
  allowed_staff_ids: [],
  available_from_minute: 600,
  available_until_minute: 1320,
  expected_minutes: 5,
  base_points: 20,
  maximum_points: 25,
  verification_method: "self_confirmation",
  estimated_impact_value: 1.5,
  estimated_impact_unit: "kWh",
  status: "available",
  claimed_by_staff_id: null,
  claimed_at: null,
  reservation_expires_at: null,
  completed_at: null,
  verification_status: "pending",
  points_awarded: 0,
  scoring_version: "score-v1",
  version: 1,
  created_at: "2026-08-29T08:00:00Z",
  updated_at: "2026-08-29T08:00:00Z",
  game_master_recommended: true,
  recommendation_reason: "Matches your successful energy challenge history.",
};

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("staff game flows", () => {
  it("creates a configured staff player", async () => {
    let profiles: StaffProfile[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/avatars")) {
        return Response.json([{ id: "associate", label: "Associate", model_file: "associate.glb", description: "Store associate" }]);
      }
      if (url.endsWith("/api/projects/project_demo/staff") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        profiles = [{ ...staff, display_name: body.display_name, normalized_name: body.display_name.toLowerCase() }];
        return Response.json(profiles[0], { status: 201 });
      }
      if (url.endsWith("/api/projects/project_demo/staff")) return Response.json(profiles);
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithClient(<StaffConfigurationPage project={project} />);
    fireEvent.click(await screen.findByRole("button", { name: "Create first staff profile" }));
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Ava" } });
    fireEvent.change(screen.getByLabelText("Join PIN"), { target: { value: "4321" } });
    fireEvent.click(screen.getByRole("button", { name: "Create player" }));

    expect(await screen.findByRole("heading", { name: "Ava" })).toBeVisible();
    const createCall = fetchMock.mock.calls.find(([input, init]) => (
      String(input).endsWith("/staff") && init?.method === "POST"
    ));
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      display_name: "Ava",
      join_pin: "4321",
      avatar_id: "associate",
      authorized_zone_ids: ["sales"],
    });
  });

  it("joins by profile and PIN, then atomically claims a task", async () => {
    let currentTask = task;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/game/join/join-token") && init?.method === "POST") {
        return Response.json({ session_token: "secret-session", expires_at: "2026-08-30T08:00:00Z", game_day: gameDay, staff });
      }
      if (url.endsWith("/api/game/join/join-token")) {
        return Response.json({
          game_day_id: gameDay.id,
          project_id: project.id,
          store_name: project.store.name,
          local_date: gameDay.local_date,
          start_minute: gameDay.start_minute,
          end_minute: gameDay.end_minute,
          status: gameDay.status,
          staff: [{ id: staff.id, display_name: staff.display_name, role: staff.role, avatar_id: staff.avatar_id }],
        });
      }
      if (url.endsWith("/api/game/tasks/task_lights/claim")) {
        currentTask = { ...currentTask, status: "claimed", claimed_by_staff_id: staff.id, version: 2 };
        return Response.json(currentTask);
      }
      if (url.endsWith("/api/game/tasks")) return Response.json([currentTask]);
      if (url.endsWith("/api/game/leaderboard")) return Response.json([]);
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithClient(<StaffGamePage joinToken="join-token" />);
    expect(await screen.findByRole("heading", { name: "Join Demo store." })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Your configured name"), { target: { value: "  AVA  " } });
    fireEvent.change(screen.getByLabelText("Private join PIN"), { target: { value: "4321" } });
    fireEvent.click(screen.getByRole("button", { name: "Enter the game" }));

    expect(await screen.findByRole("heading", { name: "Switch off unused display lights" })).toBeVisible();
    expect(screen.getByText("✦ Game Master pick")).toBeVisible();
    expect(screen.getByText("Matches your successful energy challenge history.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Snatch task" }));
    expect(await screen.findByText("Reserved for you")).toBeVisible();
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => (
      String(input).endsWith("/task_lights/claim")
      && init?.headers != null
      && Object.entries(init.headers).some(([key, value]) => key === "Authorization" && value === "Bearer secret-session")
    ))).toBe(true));
  });
});
