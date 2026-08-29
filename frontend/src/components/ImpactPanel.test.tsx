// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Distribution, ImpactAnalysis, ScenarioComparison } from "../types";
import { ImpactPanel } from "./ImpactPanel";

function distribution(p50: number): Distribution {
  return {
    label: "Test metric",
    unit: "test",
    p10: p50 - 1,
    p50,
    p90: p50 + 1,
    mean: p50,
    evidence_kind: "simulated",
    interpretation: "Test interpretation",
  };
}

const comparison = {
  energy_kwh: { baseline: 3, intervention: 2, difference: -1, percent_change: -33.3 },
  completion_rate: { baseline: 0.25, intervention: 0.75, difference: 0.5, percent_change: 200 },
  intervention_run: { metrics: { customer_service_incidents: 0 } },
} as ScenarioComparison;

const analysis: ImpactAnalysis = {
  id: "analysis-test",
  project_id: "project-test",
  scenario_id: "green-close",
  sample_count: 120,
  seed: 42,
  metrics: {
    annual_utility_savings: distribution(130),
    annual_emissions_avoided: distribution(75),
    completion_rate_change: distribution(40),
    net_operating_impact: distribution(85),
    profit_margin_impact: distribution(0.6),
    staff_minutes_change: distribution(1.5),
    customer_service_incidents: distribution(0),
  },
  assumptions: [],
  risks: [],
  calibration: {
    bill_daily_kwh: 100,
    modelled_daily_kwh: 50,
    model_coverage_ratio: 0.5,
    note: "Test calibration",
  },
};

describe("ImpactPanel", () => {
  it("shows every promised stakeholder impact", () => {
    render(<ImpactPanel comparison={comparison} analysis={analysis} />);

    for (const label of [
      "Annual utility savings",
      "Net operating impact",
      "Staff effort",
      "Consumer service",
      "Emissions avoided",
      "Task completion",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("120 simulated closes")).toBeInTheDocument();
  });
});
