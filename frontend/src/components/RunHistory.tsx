import { useState } from "react";

import type { SimulationRunSummary } from "../types";

function shortId(id: string): string {
  return id.replace(/^run_/, "").slice(0, 8).toUpperCase();
}

function runDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(status: SimulationRunSummary["status"]): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function RunHistory({
  runs,
  selectedRunId,
  loading,
  creating,
  createError,
  onSelect,
  onCreate,
}: {
  runs: SimulationRunSummary[];
  selectedRunId: string | null;
  loading: boolean;
  creating: boolean;
  createError?: string;
  onSelect: (runId: string) => void;
  onCreate: (values: { seed: number; sample_count: number }) => void;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [seed, setSeed] = useState(42);
  const [sampleCount, setSampleCount] = useState(120);
  const selected = runs.find((run) => run.id === selectedRunId) ?? runs[0];

  if (loading) {
    return (
      <section className="run-history-shell run-history-loading" aria-label="Loading simulation runs">
        <span />
        <div><i /><i /><i /></div>
      </section>
    );
  }

  const createButton = (
    <button type="button" className="run-primary-button" onClick={() => setShowCreate(true)} disabled={creating}>
      <span>＋</span> {runs.length ? "Run new simulation" : "Run simulation"}
    </button>
  );

  return (
    <>
      {!runs.length ? (
        <section className={`run-empty-state ${creating ? "is-running" : ""}`} aria-labelledby="run-empty-title">
          <div className="empty-run-visual" aria-hidden="true"><span><i /></span><b>01</b><b>02</b></div>
          <span className="kicker">Persistent run history</span>
          <h2 id="run-empty-title">{creating ? "Simulation running" : "No simulation runs yet"}</h2>
          <p>{creating
            ? "The Game Master is generating one matched baseline and Green Close comparison, then saving its complete replay and evidence snapshots."
            : "Create your first paired comparison. Situational Awareness will preserve the exact inputs, results, and event logs so the run can be replayed later without recalculation."}</p>
          {creating ? <div className="run-progress"><i /><span>Generating baseline, intervention, and uncertainty ranges…</span></div> : createButton}
          {createError && <strong className="run-create-error">{createError}</strong>}
        </section>
      ) : (
        <section className="run-history-shell" aria-label="Simulation run history">
          {runs[0] && !runs[0].configuration_current && (
            <div className="configuration-changed-banner">
              <span>!</span>
              <div><strong>Configuration changed since latest run</strong><small>Existing results remain unchanged. Create a new run to use the saved configuration.</small></div>
              <button type="button" onClick={() => setShowCreate(true)}>Create new run</button>
            </div>
          )}
          {creating && (
            <div className="run-generation-banner"><i /><span><strong>New comparison running</strong>Generating one immutable baseline + Green Close record…</span></div>
          )}
          <div className="run-history-heading">
            <div>
              <span className="kicker">Selected comparison</span>
              <h2>Run {selected ? shortId(selected.id) : "—"}</h2>
              <p>{selected ? runDate(selected.created_at) : "Select a completed run"}</p>
            </div>
            <div className="selected-run-meta">
              <span className={`run-status ${selected?.status ?? "queued"}`}><i /> {selected ? statusLabel(selected.status) : "Queued"}</span>
              <span>Seed <b>{selected?.seed ?? "—"}</b></span>
              <span>Samples <b>{selected?.sample_count ?? "—"}</b></span>
              <span>Savings <b>{selected?.estimated_savings_sgd == null ? "—" : `S$${selected.estimated_savings_sgd.toFixed(0)}/yr`}</b></span>
            </div>
            {createButton}
          </div>

          <div className="run-history-list" role="list" aria-label="Previous simulation runs">
            {runs.map((run, index) => (
              <button
                type="button"
                role="listitem"
                key={run.id}
                className={run.id === selectedRunId ? "selected" : ""}
                onClick={() => onSelect(run.id)}
              >
                <span className="run-list-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="run-list-identity"><strong>{shortId(run.id)}</strong><small>{runDate(run.created_at)}</small></span>
                <span className={`run-status ${run.status}`}><i /> {statusLabel(run.status)}</span>
                <span className="run-list-stat"><small>Seed</small><strong>{run.seed}</strong></span>
                <span className="run-list-stat"><small>Samples</small><strong>{run.sample_count}</strong></span>
                <span className="run-list-stat savings"><small>Estimated savings</small><strong>{run.estimated_savings_sgd == null ? "—" : `S$${run.estimated_savings_sgd.toFixed(0)}`}</strong></span>
                <span className={`run-config-state ${run.configuration_current ? "current" : "outdated"}`}><i /> {run.configuration_current ? "Configuration current" : "Configuration outdated"}</span>
                <span className="run-list-arrow">→</span>
              </button>
            ))}
          </div>
          {createError && <strong className="run-create-error">{createError}</strong>}
        </section>
      )}

      {showCreate && (
        <div className="modal-backdrop" role="presentation">
          <section className="run-create-modal" role="dialog" aria-modal="true" aria-labelledby="run-create-title">
            <button type="button" className="modal-close" aria-label="Close run configuration" onClick={() => setShowCreate(false)}>×</button>
            <span className="kicker">New immutable comparison</span>
            <h2 id="run-create-title">Run simulation</h2>
            <p>This creates one history record containing the matched current-close baseline and Green Close intervention. It does not overwrite prior runs.</p>
            <form onSubmit={(event) => {
              event.preventDefault();
              onCreate({ seed, sample_count: sampleCount });
              setShowCreate(false);
            }}>
              <label><span>Replay seed</span><input type="number" min="0" max="2147483647" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
              <label><span>Monte Carlo samples</span><select value={sampleCount} onChange={(event) => setSampleCount(Number(event.target.value))}>
                <option value={25}>25 · Fast validation</option>
                <option value={60}>60 · Directional</option>
                <option value={120}>120 · Recommended</option>
                <option value={250}>250 · High confidence</option>
                <option value={500}>500 · Maximum</option>
              </select></label>
              <div className="paired-run-diagram" aria-label="One paired comparison record">
                <div><i>01</i><span><strong>Current close</strong>Baseline event log</span></div>
                <b>＋</b>
                <div><i>02</i><span><strong>Green Close</strong>Intervention event log</span></div>
                <em>One run record</em>
              </div>
              <div className="run-create-actions"><button type="button" onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" className="primary">Run simulation</button></div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
