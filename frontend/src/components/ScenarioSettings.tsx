import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { updateScenarioSettings } from "../api";
import type { DemoBundle, Project, ScenarioSettings as Settings } from "../types";

export function ScenarioSettings({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState<Settings>(project.settings);
  const save = useMutation({
    mutationFn: () => updateScenarioSettings(project.id, settings),
    onSuccess: (updated) => {
      queryClient.setQueryData<DemoBundle>(["demo"], (current) => current ? { ...current, project: updated } : current);
      void queryClient.invalidateQueries({ queryKey: ["analysis"] });
    },
  });
  return (
    <details className="settings-panel">
      <summary><span><strong>Scenario assumptions</strong><small>Change operational inputs and rerun the uncertainty analysis</small></span><i>Configure</i></summary>
      <form onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <label><span>Operating days / year</span><input type="number" min="1" max="366" value={settings.operating_days_per_year} onChange={(event) => setSettings({ ...settings, operating_days_per_year: Number(event.target.value) })} /></label>
        <label><span>Labour cost (S$/hr)</span><input type="number" min="0" step="0.5" value={settings.labour_cost_sgd_per_hour} onChange={(event) => setSettings({ ...settings, labour_cost_sgd_per_hour: Number(event.target.value) })} /></label>
        <label><span>Annual revenue (S$)</span><input type="number" min="1" step="10000" value={settings.annual_revenue_sgd} onChange={(event) => setSettings({ ...settings, annual_revenue_sgd: Number(event.target.value) })} /></label>
        <label><span>Load uncertainty (±%)</span><input type="number" min="0" max="75" value={settings.equipment_load_uncertainty_pct} onChange={(event) => setSettings({ ...settings, equipment_load_uncertainty_pct: Number(event.target.value) })} /></label>
        <label><span>Tariff uncertainty (±%)</span><input type="number" min="0" max="50" value={settings.tariff_uncertainty_pct} onChange={(event) => setSettings({ ...settings, tariff_uncertainty_pct: Number(event.target.value) })} /></label>
        <label><span>Expected adoption</span><input type="range" min="0" max="1" step="0.05" value={settings.adoption_rate} onChange={(event) => setSettings({ ...settings, adoption_rate: Number(event.target.value) })} /><small>{Math.round(settings.adoption_rate * 100)}%</small></label>
        <button type="submit" disabled={save.isPending}>{save.isPending ? "Recalculating…" : "Save and recalculate"}</button>
      </form>
    </details>
  );
}
