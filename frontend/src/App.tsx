import { useMutation, useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import {
  bootstrapDemo,
  createStaffChecklist,
  downloadDecisionBrief,
  fetchComparison,
  fetchExplanations,
  runAnalysis,
} from "./api";
import { ConfigurationPage } from "./components/ConfigurationPage";
import { ImpactPanel } from "./components/ImpactPanel";
import { ReplayTimeline } from "./components/ReplayTimeline";
import { StaffHandoff } from "./components/StaffHandoff";
import type {
  SimulationEvent,
  UtilityBill,
} from "./types";
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

export default function App() {
  const [seed, setSeed] = useState(42);
  const [scenarioView, setScenarioView] = useState<"baseline" | "intervention">("intervention");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [confirmedBill, setConfirmedBill] = useState<UtilityBill | null>(null);
  const [showHandoff, setShowHandoff] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [activeView, setActiveView] = useState<"simulation" | "configuration">("simulation");

  const demo = useQuery({ queryKey: ["demo"], queryFn: bootstrapDemo, retry: 1 });
  const comparison = useQuery({
    queryKey: ["comparison", demo.data?.project.id, seed],
    queryFn: () => fetchComparison(seed, demo.data!.project.id),
    enabled: Boolean(demo.data?.project.id),
    retry: 1,
  });
  const analysis = useQuery({
    queryKey: ["analysis", demo.data?.project.id, seed],
    queryFn: () => runAnalysis(demo.data!.project.id, seed),
    enabled: Boolean(demo.data?.project.id),
    retry: 1,
  });
  const explanations = useQuery({
    queryKey: ["explanations", demo.data?.project.id, scenarioView, seed],
    queryFn: () => fetchExplanations(
      scenarioView === "baseline" ? "baseline" : "green-close",
      seed,
      demo.data!.project.id,
    ),
    enabled: Boolean(demo.data?.project.id),
    retry: 1,
  });
  const handoff = useMutation({
    mutationFn: () => createStaffChecklist(demo.data!.project.id),
    onSuccess: () => setShowHandoff(true),
  });

  const run = comparison.data
    ? scenarioView === "baseline"
      ? comparison.data.baseline_run
      : comparison.data.intervention_run
    : null;
  const project = demo.data?.project;
  const store = project?.store;
  const events = run?.events ?? [];
  const world = useMemo(
    () => (store ? buildWorld(store, events, step) : null),
    [events, step, store],
  );

  useEffect(() => {
    setPlaying(false);
    setStep(0);
  }, [scenarioView, seed]);

  const currentEvent = step > 0 ? events[step - 1] : null;
  const currentExplanation = currentEvent
    ? explanations.data?.find((item) => item.event_seq === currentEvent.seq)
    : null;
  const recentEvents = events.slice(Math.max(0, step - 4), step).reverse();
  const bill = confirmedBill ?? demo.data?.bills[0];
  const bills = demo.data?.bills ?? [];
  const loading = demo.isLoading || comparison.isLoading;
  const error = demo.error ?? comparison.error;

  if (loading) {
    return (
      <main className="loading-screen">
        <span className="brand-mark">SA</span>
        <p>Constructing the governed store model…</p>
      </main>
    );
  }

  if (error || !project || !store || !comparison.data || !world) {
    return (
      <main className="loading-screen error-screen">
        <span className="brand-mark">SA</span>
        <h1>Simulation service unavailable</h1>
        <p>{error instanceof Error ? error.message : "Start the FastAPI service on port 8000."}</p>
        <button type="button" onClick={() => window.location.reload()}>Retry connection</button>
      </main>
    );
  }

  const exportReport = async () => {
    if (!analysis.data) return;
    setExporting(true);
    try {
      const report = await downloadDecisionBrief(project.id, analysis.data.id);
      const url = URL.createObjectURL(new Blob([report], { type: "text/markdown" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "situational-awareness-decision-brief.md";
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

  return (
    <div className="product-shell">
      <aside className="sidebar">
        <div className="side-brand">
          <span className="brand-mark">SA</span>
          <div><strong>Situational</strong><span>Awareness</span></div>
        </div>
        <nav aria-label="Primary navigation">
          <button type="button" aria-label="Simulation" className={activeView === "simulation" ? "active" : ""} onClick={() => openSimulationSection("simulation")}><i>01</i><span>Simulation</span></button>
          <button type="button" aria-label="Impact" onClick={() => openSimulationSection("impact")}><i>02</i><span>Impact</span></button>
          <button type="button" aria-label="Evidence" onClick={() => openSimulationSection("evidence")}><i>03</i><span>Evidence</span></button>
          <button type="button" className={`nav-configuration ${activeView === "configuration" ? "active" : ""}`} aria-current={activeView === "configuration" ? "page" : undefined} onClick={() => { setActiveView("configuration"); window.scrollTo({ top: 0, behavior: "smooth" }); }}><i>04</i><span>Configuration</span></button>
        </nav>
        <div className="side-context">
          <span>Project</span>
          <strong>{project.name}</strong>
          <small>Singapore · {store.floor_area_m2} m²</small>
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
                <label className="seed-control">
                  <span>Replay seed</span>
                  <select value={seed} onChange={(event) => setSeed(Number(event.target.value))}>
                    <option value={42}>42 · Typical</option>
                    <option value={91}>91 · Busy close</option>
                    <option value={173}>173 · Slow adoption</option>
                  </select>
                </label>
                <button type="button" className="handoff-button" disabled={handoff.isPending} onClick={() => handoff.mutate()}>
                  {handoff.isPending ? "Creating…" : "Staff handoff"}
                </button>
                <button type="button" className="export-button" disabled={!analysis.data || exporting} onClick={exportReport}>
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
            analysis={analysis.data}
            onConfirmed={setConfirmedBill}
          />
        ) : (
          <>
          <section className="simulation-section" id="simulation">
          <div className="simulation-topline">
            <div className="scenario-switch" role="group" aria-label="Scenario shown">
              <button
                type="button"
                className={scenarioView === "baseline" ? "active" : ""}
                onClick={() => setScenarioView("baseline")}
              >
                <span>Current close</span><small>Baseline</small>
              </button>
              <button
                type="button"
                className={scenarioView === "intervention" ? "active" : ""}
                onClick={() => setScenarioView("intervention")}
              >
                <span>Green Close</span><small>Intervention</small>
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
                <StoreScene store={store} world={world} />
              </Suspense>
              <ReplayTimeline
                events={events}
                step={step}
                setStep={setStep}
                playing={playing}
                setPlaying={setPlaying}
              />
            </div>

            <aside className="game-master-panel">
              <div className="gm-heading">
                <span className="gm-orbit"><i /></span>
                <div><small>Authoritative controller</small><h2>Game Master</h2></div>
              </div>
              <div className="gm-state">
                <span>Current ruling</span>
                <strong>{currentEvent?.type.replaceAll("_", " ") ?? "Awaiting replay"}</strong>
                <p>{currentExplanation?.rationale ?? "The Game Master owns time, validates every proposed action, and writes the event ledger."}</p>
                {currentExplanation && (
                  <div className="explanation-rules">
                    {currentExplanation.rules_checked.slice(0, 3).map((rule) => <span key={rule}>{rule}</span>)}
                  </div>
                )}
              </div>
              <div className="rule-stack">
                <span>Live constraints</span>
                <div><i className="rule-ok" /><p><strong>Cold storage protected</strong><small>Cannot be switched off by any agent</small></p></div>
                <div><i className={world.customerCount ? "rule-watch" : "rule-ok"} /><p><strong>Customer loads guarded</strong><small>{world.customerCount ? "Held until the store is empty" : "Released after last exit"}</small></p></div>
                <div><i className="rule-ok" /><p><strong>Role authority enforced</strong><small>Only assigned roles can operate loads</small></p></div>
              </div>
              <div className="event-ledger">
                <div className="ledger-title"><span>Event ledger</span><small>append-only</small></div>
                {recentEvents.length ? recentEvents.map((event) => (
                  <div className="ledger-event" key={event.seq}>
                    <i className={`tone-${eventTone(event.type)}`} />
                    <p><strong>{event.message}</strong><small>#{event.seq} · {event.at_minute}</small></p>
                  </div>
                )) : <p className="ledger-empty">Play the simulation to inspect validated state changes.</p>}
              </div>
            </aside>
          </div>
          </section>

          <ImpactPanel comparison={comparison.data} analysis={analysis.data} />

          <section className="evidence-section" id="evidence">
          <div className="section-heading">
            <div><span className="kicker">Traceable inputs</span><h2>Evidence boundary</h2></div>
            <span className="evidence-badge evidence-confirmed">Confirmed source</span>
          </div>
          <div className="evidence-layout">
            <article className="bill-card">
              <div className="document-icon">kWh</div>
              <div>
                <span>Synthetic utility bill</span>
                <strong>{bill?.period_start} — {bill?.period_end}</strong>
                <small>{bill?.total_kwh.toLocaleString()} kWh · S${bill?.total_cost_sgd.toLocaleString()} · raw file not retained</small>
              </div>
            </article>
            <article className="calibration-card">
              <span>Model coverage</span>
              <strong>{analysis.data ? `${(analysis.data.calibration.model_coverage_ratio * 100).toFixed(0)}%` : "—"}</strong>
              <p>Closing equipment is deliberately a bounded subsystem, not a forced fit to whole-store usage.</p>
            </article>
            <article className="evidence-legend">
              <div><i className="evidence-measured" /><span><strong>Measured</strong>Bill totals after confirmation</span></div>
              <div><i className="evidence-derived" /><span><strong>Derived</strong>Effective tariff and deltas</span></div>
              <div><i className="evidence-assumed" /><span><strong>Assumed</strong>Equipment loads and operating days</span></div>
              <div><i className="evidence-simulated" /><span><strong>Simulated</strong>Behaviour and event outcomes</span></div>
            </article>
          </div>
          </section>
          </>
        )}
      </main>
      {showHandoff && handoff.data && <StaffHandoff checklist={handoff.data} onClose={() => setShowHandoff(false)} />}
    </div>
  );
}
