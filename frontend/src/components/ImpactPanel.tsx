import type { ImpactAnalysis, ScenarioComparison } from "../types";

function signed(value: number, suffix = ""): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}${suffix}`;
}

function RangeBar({ p10, p50, p90 }: { p10: number; p50: number; p90: number }) {
  const max = Math.max(Math.abs(p10), Math.abs(p50), Math.abs(p90), 1);
  const medianPosition = Math.min(100, Math.max(0, (p50 / max) * 100));
  return (
    <div className="range-bar" aria-label={`P10 ${p10}, median ${p50}, P90 ${p90}`}>
      <span className="range-fill" />
      <i style={{ left: `${medianPosition}%` }} />
    </div>
  );
}

export function ImpactPanel({
  comparison,
  analysis,
}: {
  comparison: ScenarioComparison;
  analysis?: ImpactAnalysis;
}) {
  const savings = analysis?.metrics.annual_utility_savings;
  const emissions = analysis?.metrics.annual_emissions_avoided;
  const completion = analysis?.metrics.completion_rate_change;
  const net = analysis?.metrics.net_operating_impact;
  const margin = analysis?.metrics.profit_margin_impact;
  const staff = analysis?.metrics.staff_minutes_change;
  const consumer = analysis?.metrics.customer_service_incidents;
  return (
    <section className="impact-section" aria-labelledby="impact-title">
      <div className="section-heading">
        <div>
          <span className="kicker">Matched-seed comparison</span>
          <h2 id="impact-title">Decision impact</h2>
        </div>
        <span className="evidence-badge">{analysis?.sample_count ?? "…"} simulated closes</span>
      </div>
      <div className="impact-grid">
        <article className="impact-card impact-primary">
          <span>Annual utility savings</span>
          <strong>{savings ? `S$${savings.p50.toFixed(0)}` : "Calculating…"}</strong>
          {savings && (
            <>
              <RangeBar p10={savings.p10} p50={savings.p50} p90={savings.p90} />
              <small>P10 S${savings.p10.toFixed(0)} · P90 S${savings.p90.toFixed(0)}</small>
            </>
          )}
        </article>
        <article className="impact-card">
          <span>Net operating impact</span>
          <strong>{net ? `${net.p50 < 0 ? "−" : "+"}S$${Math.abs(net.p50).toFixed(0)}` : "Calculating…"}</strong>
          <small>{margin ? `${signed(margin.p50)} basis points of assumed annual revenue` : "Utility savings less incremental overtime"}</small>
        </article>
        <article className="impact-card">
          <span>Staff effort</span>
          <strong>{staff ? signed(staff.p50, " min") : "Calculating…"}</strong>
          <small>Median additional task interaction time per close</small>
        </article>
        <article className="impact-card">
          <span>Consumer service</span>
          <strong>{consumer ? consumer.p50.toFixed(0) : comparison.intervention_run.metrics.customer_service_incidents}</strong>
          <small>Median incidents per close; unsafe actions are blocked</small>
        </article>
        <article className="impact-card">
          <span>Emissions avoided</span>
          <strong>{emissions ? `${emissions.p50.toFixed(0)} kg` : "Calculating…"}</strong>
          <small>Operational CO₂e per year, median estimate</small>
        </article>
        <article className="impact-card">
          <span>Task completion</span>
          <strong>{completion ? signed(completion.p50, " pp") : signed(comparison.completion_rate.difference * 100, " pp")}</strong>
          <small>{Math.abs(comparison.energy_kwh.difference).toFixed(2)} kWh avoided in this replay</small>
        </article>
      </div>
      <p className="uncertainty-note">
        Ranges combine equipment-load, tariff, adoption, and behavioural uncertainty. A pilot is
        still required before treating these figures as forecast savings.
      </p>
    </section>
  );
}
