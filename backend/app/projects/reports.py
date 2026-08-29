from __future__ import annotations

from .models import ImpactAnalysis, Project, UtilityBill


def build_decision_brief(project: Project, bill: UtilityBill, analysis: ImpactAnalysis) -> str:
    utility = analysis.metrics["annual_utility_savings"]
    energy = analysis.metrics["annual_energy_saved"]
    emissions = analysis.metrics["annual_emissions_avoided"]
    net = analysis.metrics["net_operating_impact"]
    margin = analysis.metrics["profit_margin_impact"]
    completion = analysis.metrics["completion_rate_change"]
    staff = analysis.metrics["staff_minutes_change"]
    consumer = analysis.metrics["customer_service_incidents"]
    recommendation = (
        "Proceed to a time-boxed in-store pilot with sub-metering and staff feedback."
        if completion.p50 > 0 and net.p50 >= 0
        else "Refine the intervention assumptions before starting an in-store pilot."
    )
    assumptions = "\n".join(
        f"- **{item.label}:** {item.value} {item.unit or ''} — {item.kind}; {item.source}"
        for item in analysis.assumptions
    )
    risks = "\n".join(f"- {risk}" for risk in analysis.risks)
    return f"""# Situational Awareness — Decision Brief

## {project.name}: Green Close

**Recommendation:** {recommendation}

This is a simulation-supported pilot decision, not a guaranteed savings forecast. Results use
{analysis.sample_count} matched-seed closes and report P10/P50/P90 uncertainty.

## Expected impact

| Outcome | P10 | P50 | P90 | Unit |
|---|---:|---:|---:|---|
| Annual energy avoided | {energy.p10:.1f} | {energy.p50:.1f} | {energy.p90:.1f} | {energy.unit} |
| Annual utility savings | {utility.p10:.1f} | {utility.p50:.1f} | {utility.p90:.1f} | {utility.unit} |
| Annual emissions avoided | {emissions.p10:.1f} | {emissions.p50:.1f} | {emissions.p90:.1f} | {emissions.unit} |
| Net operating impact | {net.p10:.1f} | {net.p50:.1f} | {net.p90:.1f} | {net.unit} |
| Profit-margin impact | {margin.p10:.2f} | {margin.p50:.2f} | {margin.p90:.2f} | {margin.unit} |
| Task-completion change | {completion.p10:.1f} | {completion.p50:.1f} | {completion.p90:.1f} | {completion.unit} |
| Staff effort change | {staff.p10:.1f} | {staff.p50:.1f} | {staff.p90:.1f} | {staff.unit} |
| Customer-service incidents | {consumer.p10:.1f} | {consumer.p50:.1f} | {consumer.p90:.1f} | {consumer.unit} |

## Evidence boundary

- Confirmed bill: `{bill.filename}`, {bill.period_start} to {bill.period_end},
  {bill.total_kwh:,.0f} kWh and S${bill.total_cost_sgd:,.2f}.
- The raw utility file was not retained after extraction.
- The bill calibrates the effective tariff; it does not prove individual equipment loads.
- The Three.js replay is reconstructed from the authoritative Game Master event ledger.

## Assumptions

{assumptions}

## Risks and exclusions

{risks}

## Pilot design

1. Validate the equipment inventory and protected-load list with facilities staff.
2. Run a two-week baseline with plug-level or circuit sub-metering.
3. Pilot Green Close in one comparable store for two weeks.
4. Track completion, exceptions, customer incidents, staff time, and after-hours kWh.
5. Recalibrate the model and make the rollout decision using observed results.

---

Analysis ID: `{analysis.id}` · Simulation seed: `{analysis.seed}`
"""
