import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { testAIProvider, updateAgentSettings } from "../api";
import type {
  AIStatus,
  AgentIntelligenceSettings,
  AgentMode,
  DemoBundle,
  Project,
} from "../types";

const modeLabels: Record<AgentMode, { title: string; eyebrow: string }> = {
  deterministic: { title: "Deterministic", eyebrow: "Reproducible" },
  openai: { title: "OpenAI", eyebrow: "Cloud provider" },
  ollama: { title: "Local Ollama", eyebrow: "Local provider" },
};

export function AgentIntelligence({
  project,
  status,
  statusLoading,
}: {
  project: Project;
  status?: AIStatus;
  statusLoading: boolean;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<AgentIntelligenceSettings>(project.agent_settings);
  useEffect(() => setValues(project.agent_settings), [project.agent_settings]);

  const modes = useMemo(() => status?.modes ?? [], [status]);
  const selectedStatus = modes.find((item) => item.mode === values.mode);
  const selectMode = (mode: AgentMode) => {
    const provider = modes.find((item) => item.mode === mode);
    setValues({
      ...values,
      mode,
      model: mode === "deterministic" ? null : provider?.model ?? null,
    });
  };

  const save = useMutation({
    mutationFn: () => updateAgentSettings(project.id, values),
    onSuccess: (updated) => {
      queryClient.setQueryData<DemoBundle>(["demo"], (current) => (
        current ? { ...current, project: updated } : current
      ));
    },
  });
  const connection = useMutation({
    mutationFn: () => testAIProvider({
      mode: values.mode,
      model: values.model,
      timeout_seconds: values.timeout_seconds,
    }),
  });

  return (
    <section className="config-card agent-intelligence-card">
      <div className="config-card-heading">
        <div><span>03 · Agent intelligence</span><h2>Decision provider</h2></div>
        <small>Game Master remains authoritative</small>
      </div>

      <div className="provider-grid" aria-label="Agent intelligence modes">
        {(["deterministic", "openai", "ollama"] as AgentMode[]).map((mode) => {
          const provider = modes.find((item) => item.mode === mode);
          const selectable = mode === "deterministic" || Boolean(provider?.configured);
          return (
            <button
              type="button"
              key={mode}
              className={values.mode === mode ? "selected" : ""}
              aria-pressed={values.mode === mode}
              disabled={!selectable || statusLoading}
              onClick={() => selectMode(mode)}
            >
              <span className="provider-card-top"><i /><em>{modeLabels[mode].eyebrow}</em></span>
              <strong>{modeLabels[mode].title}</strong>
              <small>{statusLoading ? "Checking backend…" : provider?.detail ?? "Status unavailable"}</small>
              <span className={`provider-availability ${provider?.available ? "available" : "unavailable"}`}>
                {provider?.available ? "Available" : mode === "deterministic" ? "Available" : "Unavailable"}
              </span>
            </button>
          );
        })}
      </div>

      <div className="agent-provider-summary">
        <div><span>Selected provider</span><strong>{modeLabels[values.mode].title}</strong></div>
        <div><span>Model</span><strong>{selectedStatus?.model ?? (values.mode === "deterministic" ? "Rules engine" : "Not configured")}</strong></div>
        <button type="button" disabled={connection.isPending} onClick={() => connection.mutate()}>
          {connection.isPending ? "Testing…" : "Test connection"}
        </button>
      </div>
      {connection.data && (
        <p className={`provider-test-result ${connection.data.success ? "success" : "error"}`}>
          <i /> <strong>{connection.data.success ? "Connection verified" : "Connection unavailable"}</strong>
          <span>{connection.data.success
            ? `${connection.data.provider} · ${Math.round(connection.data.latency_ms)} ms · structured proposal accepted`
            : connection.data.error}</span>
        </p>
      )}

      <form className="agent-budget-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <div className="agent-budget-heading"><span>Run guardrails</span><small>Applied across the paired comparison</small></div>
        <label><span>Maximum calls / run</span><input type="number" min="0" max="200" value={values.max_calls} onChange={(event) => setValues({ ...values, max_calls: Number(event.target.value) })} /></label>
        <label><span>Calls / agent</span><input type="number" min="0" max="50" value={values.max_calls_per_agent} onChange={(event) => setValues({ ...values, max_calls_per_agent: Number(event.target.value) })} /></label>
        <label><span>Timeout (seconds)</span><input type="number" min="0.25" max="60" step="0.25" value={values.timeout_seconds} onChange={(event) => setValues({ ...values, timeout_seconds: Number(event.target.value) })} /></label>
        <label><span>Concurrency</span><input type="number" min="1" max="8" value={values.max_concurrency} onChange={(event) => setValues({ ...values, max_concurrency: Number(event.target.value) })} /></label>
        <label><span>Token budget</span><input type="number" min="0" max="1000000" step="100" value={values.token_budget} onChange={(event) => setValues({ ...values, token_budget: Number(event.target.value) })} /></label>
        <label><span>Estimated cost cap (US$)</span><input type="number" min="0" max="1000" step="0.01" value={values.cost_budget_usd} onChange={(event) => setValues({ ...values, cost_budget_usd: Number(event.target.value) })} /></label>
        <div className="config-form-actions agent-settings-actions">
          <span className={save.isError ? "save-state error" : "save-state"}>
            {save.isError ? save.error.message : save.isSuccess ? "Saved as run defaults" : "Budgets stop additional calls and trigger labelled fallback"}
          </span>
          <button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save intelligence settings"}</button>
        </div>
      </form>

      <div className="provider-privacy-note">
        <span>⌁</span>
        <p><strong>Credentials stay on the backend</strong>No API-key field is exposed here. Operators configure OPENAI_API_KEY and model names through backend environment variables. Only public rationales, usage, latency, and safe configuration fingerprints are persisted.</p>
      </div>
      <p className="provider-cost-note">Cost is an estimate, not billing data. OpenAI estimates are zero unless backend per-token rates are configured; local Ollama is recorded as US$0.</p>
    </section>
  );
}
