// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GameLearningPanel } from "./GameLearningPanel";
import type { GameDayAnalysis, LearnedGamePolicy } from "../types";


const policy: LearnedGamePolicy = {
  version: "staff-game-policy-2026-08-30-abc123",
  project_id: "project_demo",
  previous_version: "staff-game-policy-2026.08",
  source_game_day_id: "day_abc123",
  prompt_template_version: "staff-game-learning-2026.08",
  prompt_context: ["Previous task completion: 0/1 released tasks."],
  domain_point_multipliers: {
    energy: 1.05,
    water: 1,
    waste: 1,
    food: 1,
    transport: 1,
    buying: 1,
  },
  guardrails: ["Never create tasks for protected equipment."],
  active: true,
  created_at: "2026-08-30T00:00:00Z",
};

const analysis: GameDayAnalysis = {
  id: "analysis_1",
  project_id: "project_demo",
  game_day_id: "day_abc123",
  analyzer_mode: "deterministic",
  provider: "deterministic",
  model: "staff-game-learning-rules",
  fallback_used: false,
  prompt_template_version: "staff-game-learning-2026.08",
  metrics: {
    active_staff_profiles: 2,
    participating_staff: 1,
    tasks_released: 1,
    tasks_claimed: 1,
    tasks_completed: 0,
    tasks_released_back: 1,
    completion_rate: 0,
    total_points: 0,
    estimated_impact_total: 0,
    domain_performance: {
      energy: { released: 1, claimed: 1, completed: 0, completion_rate: 0, estimated_impact: 0, impact_unit: null },
    },
  },
  narrative: {
    summary: "One staff player participated and the released task was not completed.",
    patterns: ["One claimed task was returned to the pool."],
    recommendations: ["Clarify the challenge and test it again."],
  },
  learned_policy_version: policy.version,
  created_at: "2026-08-30T00:00:00Z",
};

afterEach(cleanup);

describe("GameLearningPanel", () => {
  it("shows evidence, bounded changes, and inspectable prompt guardrails", () => {
    render(<GameLearningPanel analysis={analysis} policy={policy} loading={false} />);

    expect(screen.getByRole("heading", { name: "End-of-day Game Master analysis" })).toBeVisible();
    expect(screen.getByText("1.05×")).toHaveClass("adjusted");
    expect(screen.getByText("engagement only")).toBeVisible();

    fireEvent.click(screen.getByText("Inspect learned prompt context and guardrails"));
    expect(screen.getByText("Previous task completion: 0/1 released tasks.")).toBeVisible();
    expect(screen.getByText("Never create tasks for protected equipment.")).toBeVisible();
  });
});
