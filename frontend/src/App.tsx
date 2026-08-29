import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import {
  bootstrapDemo,
  createSimulationRun,
  createStaffChecklist,
  downloadRunDecisionBrief,
  fetchSimulationRun,
  listSimulationRuns,
} from "./api";
import { ConfigurationPage } from "./components/ConfigurationPage";
import { ImpactPanel } from "./components/ImpactPanel";
import { ReplayTimeline } from "./components/ReplayTimeline";
import { RunHistory } from "./components/RunHistory";
import { StaffHandoff } from "./components/StaffHandoff";
import type { PersistedSimulationRun, SimulationEvent, SimulationRunSummary, UtilityBill } from "./types";
import { buildWorld } from "./world";

const StoreScene = lazy(() =>
  import("./components/StoreScene").then((module) => ({ default: module.StoreScene })),
);

function eventTone(type: string): string {
  if (type.includes("rejected")) return "blocked";
  if (type.includes("equipment") || type.includes("checklist")) return "accepted";
  if (type.includes("customer")) return "consumer";
  return "neutral";
}

function shortRunId(runId: string): string {
  return runId.replace(/^run_/, "").slice(0, 8).toUpperCase();
}

const FALLBACK_GAME_MASTER_RULES: PersistedSimulationRun["game_master_rules_snapshot"] = [
  { id: "protected_loads", label: "Protected loads stay active", description: "Protected equipment cannot be switched off by any agent." },
  { id: "role_authorization", label: "Role authorization enforced", description: "Only assigned roles may operate an equipment load." },
  { id: "customer_presence", label: "Customer-facing loads guarded", description: "Customer-facing equipment stays active until every consumer exits." },
  { id: "immutable_snapshot", label: "Historical inputs locked", description: "A replay always uses the configuration and evidence stored with its run." },
];

function summarizeRun(run: PersistedSimulationRun): SimulationRunSummary {
  return {
    id: run.id,
    project_id: run.project_id,
    created_at: run.created_at,
    completed_at: run.completed_at,
    status: run.status,
    seed: run.seed,
    sample_count: run.sample_count,
    estimated_savings_sgd: run.impact_analysis?.metrics.annual_utility_savings?.p50 ?? null,
    configuration_current: run.configuration_current,
    game_master_rules_version: run.game_master_rules_version,
    failure_message: run.failure_message,
  };
}

export default function App() {
  const queryClient = useQueryClient();
  const [scenarioView, setScenarioView] = useState<"baseline" | "intervention">("intervention");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [confirmedBill, setConfirmedBill] = useState<UtilityBill | null>(null);
  const [showHandoff, setShowHandoff] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [activeView, setActiveView] = useState<"simulation" | "configuration">("simulation");

  const demo = useQuery({ queryKey: ["demo"], queryFn: bootstrapDemo, retry: 1 });
  const project = demo.data?.project;
  const runs = useQuery({
    queryKey: ["runs", project?.id],
    queryFn: () => listSimulationRuns(project!.id),
    enabled: Boolean(project?.id),
    retry: 1,
  });
  const selectedRun = useQuery({
    queryKey: ["run", project?.id, selectedRunId],
    queryFn: () => fetchSimulationRun(project!.id, selectedRunId!),
    enabled: Boolean(project?.id && selectedRunId),
    retry: 1,
  });
  const createRun = useMutation({
    mutationFn: (values: { seed: number; sample_count: number }) => (
      createSimulationRun(project!.id, values)
    ),
    onSuccess: (created) => {
      queryClient.setQueryData<SimulationRunSummary[]>(
        ["runs", project!.id],
        (current = []) => [summarizeRun(created), ...current.filter((run) => run.id !== created.id)],
      );
      queryClient.setQueryData<PersistedSimulationRun>(
        ["run", project!.id, created.id],
        created,
      );
      setSelectedRunId(created.id);
    },
  });
  const handoff = useMutation({
    mutationFn: () => createStaffChecklist(project!.id),
    onSuccess: () => setShowHandoff(true),
  });

  useEffect(() => {
    const history = runs.data ?? [];
    if (!history.length) {
      if (!createRun.isPending) setSelectedRunId(null);
      return;
    }
    const selectedRunIsCached = selectedRunId
      ? Boolean(queryClient.getQueryData(["run", project?.id, selectedRunId]))
      : false;
    if (!selectedRunId || (!history.some((run) => run.id === selectedRunId) && !selectedRunIsCached)) {
      setSelectedRunId(history[0].id);
    }
  }, [createRun.isPending, project?.id, queryClient, runs.data, selectedRunId]);

  useEffect(() => {
    setPlaying(false);
    setStep(0);
  }, [scenarioView, selectedRunId]);

  const persistedRun = selectedRun.data;
  const gameMasterRules = persistedRun?.game_master_rules_snapshot.length
    ? persistedRun.game_master_rules_snapshot
    : FALLBACK_GAME_MASTER_RULES;
  const comparison = persistedRun?.status === "completed" ? persistedRun.comparison : null;
  const run = comparison
    ? scenarioView === "baseline"
      ? comparison.baseline_run
      : comparison.intervention_run
    : null;
  const replayStore = persistedRun?.store_snapshot;
  const events = run?.events ?? [];
  const world = useMemo(
    () => (replayStore && run ? buildWorld(replayStore, events, step) : null),
    [events, replayStore, run, step],
  );
  const explanations = scenarioView === "baseline"
    ? persistedRun?.baseline_explanations
    : persistedRun?.intervention_explanations;
  const currentEvent = step > 0 ? events[step - 1] : null;
  const currentExplanation = currentEvent
    ? explanations?.find((item) => item.event_seq === currentEvent.seq)
    : null;
  const recentEvents = events.slice(Math.max(0, step - 4), step).reverse();
  const bills = demo.data?.bills ?? [];
  const evidence = persistedRun?.evidence_snapshot;
  const analysis = persistedRun?.impact_analysis ?? undefined;
  const loading = demo.isLoading;
  const error = demo.error;

  if (loading) {
    return (
      <main className="loading-screen">
        <span className="brand-mark">SA</span>
        <p>Loading the project and run history…</p>
      </main>
    );
  }

  if (error || !project) {
    return (
      <main className="loading-screen error-screen">
        <span className="brand-mark">SA</span>
        <h1>Project service unavailable</h1>
        <p>{error instanceof Error ? error.message : "Start the FastAPI service on port 8000."}</p>
        <button type="button" onClick={() => window.location.reload()}>Retry connection</button>
      </main>
    );
  }

  const exportReport = async () => {
    if (!persistedRun?.impact_analysis) return;
    setExporting(true);
    try {
      const report = await downloadRunDecisionBrief(project.id, persistedRun.id);
      const url = URL.createObjectURL(new Blob([report], { type: "text/markdown" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `situational-awareness-${persistedRun.id}-decision-brief.md`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const openSimulationSection = (sectionId: "simulation" | "impact" | "evidence") => {
    setActiveView("simulation");
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => document.getElementById(sectionId)?.scrollIntoView());
    });
  };

  const completedSelection = Boolean(comparison && replayStore && world);

  return (
    <div className="product-shell">
      <aside className="sidebar">
        <div className="side-brand">
          <span className="brand-mark">SA</span>
          <div><strong>Situational</strong><span>Awareness</span></div>
        </div>
        <nav aria-label="Primary navigation">
          <button type="button" aria-label="Simulation" className={activeView === "simulation" ? "active" : ""} onClick={() => openSimulationSection("simulation")}><i>01</i><span>Simulation</span></button>
          <button type="button" aria-label="Impact" disabled={!completedSelection} onClick={() => openSimulationSection("impact")}><i>02</i><span>Impact</span></button>
          <button type="button" aria-label="Evidence" disabled={!completedSelection} onClick={() => openSimulationSection("evidence")}><i>03</i><span>Evidence</span></button>
          <button type="button" className={`nav-configuration ${activeView === "configuration" ? "active" : ""}`} aria-current={activeView === "configuration" ? "page" : undefined} onClick={() => { setActiveView("configuration"); window.scrollTo({ top: 0, behavior: "smooth" }); }}><i>04</i><span>Configuration</span></button>
        </nav>
        <div className="side-context">
          <span>Project</span>
          <strong>{project.name}</strong>
          <small>Singapore · {project.store.floor_area_m2} m²</small>
        </div>
        <div className="connection-state"><i /> Engine connected</div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <span className="breadcrumb">Projects / {project.name}</span>
            <h1>{activeView === "configuration" ? "Store configuration" : "Closing transition simulator"}</h1>
          </div>
          <div className="header-actions">
            {activeView === "configuration" ? (
              <button type="button" className="back-simulation-button" onClick={() => openSimulationSection("simulation")}><span>←</span> Back to simulation</button>
            ) : (
              <>
                {persistedRun && <span className="header-run-badge">Run {shortRunId(persistedRun.id)}</span>}
                <button type="button" className="handoff-button" disabled={handoff.isPending} onClick={() => handoff.mutate()}>
                  {handoff.isPending ? "Creating…" : "Staff handoff"}
                </button>
                <button type="button" className="export-button" disabled={!persistedRun?.impact_analysis || exporting} onClick={exportReport}>
                  {exporting ? "Preparing…" : "Export brief"}
                </button>
              </>
            )}
          </div>
        </header>

        {activeView === "configuration" ? (
          <ConfigurationPage
            project={project}
            bills={confirmedBill ? [confirmedBill, ...bills] : bills}
            analysis={analysis}
            onConfirmed={setConfirmedBill}
          />
        ) : (
          <>
            <section className="simulation-section" id="simulation">
              <RunHistory
                runs={runs.data ?? []}
                selectedRunId={selectedRunId}
                loading={runs.isLoading}
                creating={createRun.isPending}
                createError={createRun.error instanceof Error ? createRun.error.message : undefined}
                onSelect={setSelectedRunId}
                onCreate={(values) => createRun.mutate(values)}
              />

              {runs.error && (
                <section className="run-state-panel failed"><span>!</span><div><h2>Run history unavailable</h2><p>{runs.error.message}</p></div></section>
              )}
              {selectedRunId && selectedRun.isLoading && (
                <section className="run-state-panel loading"><span><i /></span><div><h2>Loading stored run</h2><p>Retrieving immutable snapshots and event logs…</p></div></section>
              )}
              {persistedRun?.status === "failed" && (
                <section className="run-state-panel failed"><span>!</span><div><h2>Simulation failed</h2><p>{persistedRun.failure_message ?? "The run could not be completed."}</p></div></section>
              )}
              {persistedRun && ["queued", "running"].includes(persistedRun.status) && (
                <section className="run-state-panel running"><span><i /></span><div><h2>Simulation {persistedRun.status}</h2><p>The paired comparison record is already persisted and will remain visible if generation fails.</p></div></section>
              )}

              {completedSelection && comparison && replayStore && world && (
                <>
                  <div className="simulation-topline historical-topline">
                    <div className="scenario-switch" role="group" aria-label="Scenario shown">
                      <button type="button" className={scenarioView === "baseline" ? "active" : ""} onClick={() => setScenarioView("baseline")}>
                        <span>Current close</span><small>Stored baseline</small>
                      </button>
                      <button type="button" className={scenarioView === "intervention" ? "active" : ""} onClick={() => setScenarioView("intervention")}>
                        <span>Green Close</span><small>Stored intervention</small>
                      </button>
                    </div>
                    <div className="live-facts">
                      <span><b>{world.customerCount}</b> consumers inside</span>
                      <span><b>{Object.values(world.equipmentStates).filter((state) => state === "on").length}</b> active loads</span>
                      <span><b>{scenarioView === "intervention" ? "ON" : "OFF"}</b> team nudge</span>
                    </div>
                  </div>

                  <div className="simulation-layout">
                    <div className="scene-column">
                      <Suspense fallback={<div className="scene-loading">Loading three-dimensional store…</div>}>
                        <StoreScene store={replayStore} world={world} />
                      </Suspense>
                      <ReplayTimeline events={events} step={step} setStep={setStep} playing={playing} setPlaying={setPlaying} />
                    </div>

                    <aside className="game-master-panel">
                      <div className="gm-heading">
                        <span className="gm-orbit"><i /></span>
                        <div><small>{persistedRun.game_master_rules_version}</small><h2>Game Master</h2></div>
                      </div>
                      <div className="gm-state">
                        <span>Current ruling</span>
                        <strong>{currentEvent?.type.replaceAll("_", " ") ?? "Stored replay ready"}</strong>
                        <p>{currentExplanation?.rationale ?? "Play replay to inspect the selected run’s existing event ledger. No simulation is recalculated."}</p>
                        {currentExplanation && <div className="explanation-rules">{currentExplanation.rules_checked.slice(0, 3).map((rule) => <span key={rule}>{rule}</span>)}</div>}
                      </div>
                      <div className="rule-stack">
                        <span>Snapshot constraints</span>
                        {gameMasterRules.map((rule) => (
                          <div key={rule.id}>
                            <i className={rule.id === "customer_presence" && world.customerCount ? "rule-watch" : "rule-ok"} />
                            <p>
                              <strong>{rule.label}</strong>
                              <small>{rule.id === "customer_presence"
                                ? world.customerCount ? "Held until the store is empty" : "Released after last exit"
                                : rule.description}</small>
                            </p>
                          </div>
                        ))}
                      </div>
                      <div className="event-ledger">
                        <div className="ledger-title"><span>Event ledger</span><small>immutable</small></div>
                        {recentEvents.length ? recentEvents.map((event: SimulationEvent) => (
                          <div className="ledger-event" key={event.seq}><i className={`tone-${eventTone(event.type)}`} /><p><strong>{event.message}</strong><small>#{event.seq} · {event.at_minute}</small></p></div>
                        )) : <p className="ledger-empty">Play replay to inspect the stored, validated state changes.</p>}
                      </div>
                    </aside>
                  </div>
                </>
              )}
            </section>

            {completedSelection && comparison && (
              <ImpactPanel comparison={comparison} analysis={analysis} />
            )}

            {completedSelection && persistedRun && (
              <section className="evidence-section" id="evidence">
                <div className="section-heading">
                  <div><span className="kicker">Run snapshot</span><h2>Evidence boundary</h2></div>
                  <span className="evidence-badge evidence-confirmed">Immutable source</span>
                </div>
                <div className="evidence-layout">
                  <article className="bill-card">
                    <div className="document-icon">kWh</div>
                    <div>
                      <span>{evidence ? "Confirmed utility bill" : "No evidence attached"}</span>
                      <strong>{evidence ? `${evidence.period_start} — ${evidence.period_end}` : "Simulation-only run"}</strong>
                      <small>{evidence ? `${evidence.total_kwh.toLocaleString()} kWh · S$${evidence.total_cost_sgd.toLocaleString()} · raw file not retained` : "Impact uncertainty was not calculated for this run."}</small>
                    </div>
                  </article>
                  <article className="calibration-card">
                    <span>Model coverage</span>
                    <strong>{analysis ? `${(analysis.calibration.model_coverage_ratio * 100).toFixed(0)}%` : "—"}</strong>
                    <p>{analysis?.calibration.note ?? "Attach and confirm a utility bill before creating the next run."}</p>
                  </article>
                  <article className="evidence-legend">
                    <div><i className="evidence-measured" /><span><strong>Measured</strong>Confirmed bill snapshot</span></div>
                    <div><i className="evidence-derived" /><span><strong>Derived</strong>Tariff and stored deltas</span></div>
                    <div><i className="evidence-assumed" /><span><strong>Assumed</strong>Store and scenario snapshot</span></div>
                    <div><i className="evidence-simulated" /><span><strong>Simulated</strong>Immutable paired outcomes</span></div>
                  </article>
                </div>
              </section>
            )}
          </>
        )}
      </main>
      {showHandoff && handoff.data && <StaffHandoff checklist={handoff.data} onClose={() => setShowHandoff(false)} />}
    </div>
  );
}
