from __future__ import annotations

import random
from copy import deepcopy
from datetime import UTC, datetime
from statistics import mean
from uuid import uuid4

from ..simulation import GameMaster, get_scenario
from .models import (
    Distribution,
    EvidenceKind,
    ImpactAnalysis,
    ImpactAssumption,
    Project,
    UtilityBill,
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _distribution(
    label: str,
    unit: str,
    values: list[float],
    interpretation: str,
) -> Distribution:
    return Distribution(
        label=label,
        unit=unit,
        p10=round(_percentile(values, 0.1), 2),
        p50=round(_percentile(values, 0.5), 2),
        p90=round(_percentile(values, 0.9), 2),
        mean=round(mean(values), 2),
        evidence_kind=EvidenceKind.SIMULATED,
        interpretation=interpretation,
    )


def analyse_project(
    project: Project,
    bill: UtilityBill,
    *,
    samples: int,
    seed: int,
) -> ImpactAnalysis:
    settings = project.settings
    rng = random.Random(seed)
    tariff = bill.average_tariff_sgd_per_kwh
    uncertainty = settings.equipment_load_uncertainty_pct / 100
    tariff_uncertainty = settings.tariff_uncertainty_pct / 100

    energy_saved: list[float] = []
    cost_saved: list[float] = []
    emissions_avoided: list[float] = []
    net_operating_impact: list[float] = []
    profit_margin_impact: list[float] = []
    completion_change: list[float] = []
    staff_minutes_change: list[float] = []
    customer_service_incidents: list[float] = []

    for index in range(samples):
        store = deepcopy(project.store)
        equipment_multiplier = rng.triangular(1 - uncertainty, 1 + uncertainty, 1)
        sampled_tariff = rng.triangular(
            tariff * (1 - tariff_uncertainty),
            tariff * (1 + tariff_uncertainty),
            tariff,
        )
        for equipment in store.equipment:
            equipment.power_kw_by_state = {
                state: power * equipment_multiplier
                for state, power in equipment.power_kw_by_state.items()
            }
        store.tariff_sgd_per_kwh = sampled_tariff

        baseline = GameMaster(store, get_scenario("baseline"), seed + index).run()
        intervention_scenario = get_scenario(settings.scenario_id)
        adoption_multiplier = rng.triangular(
            max(0.25, settings.adoption_rate - 0.15),
            min(1, settings.adoption_rate + 0.15),
            settings.adoption_rate,
        )
        intervention_scenario.intervention.clarity *= adoption_multiplier
        intervention_scenario.intervention.social_norm_strength *= adoption_multiplier
        intervention = GameMaster(store, intervention_scenario, seed + index).run()

        daily_kwh = max(0, baseline.metrics.after_hours_kwh - intervention.metrics.after_hours_kwh)
        annual_kwh = daily_kwh * settings.operating_days_per_year
        annual_cost = annual_kwh * sampled_tariff
        annual_emissions = annual_kwh * store.grid_emission_factor_kg_per_kwh
        overtime_delta_hours = max(
            0, intervention.metrics.overtime_minutes - baseline.metrics.overtime_minutes
        ) / 60
        labour_cost = (
            overtime_delta_hours
            * settings.labour_cost_sgd_per_hour
            * settings.operating_days_per_year
        )

        energy_saved.append(annual_kwh)
        cost_saved.append(annual_cost)
        emissions_avoided.append(annual_emissions)
        sample_net_impact = annual_cost - labour_cost
        net_operating_impact.append(sample_net_impact)
        profit_margin_impact.append(sample_net_impact / settings.annual_revenue_sgd * 10_000)
        completion_change.append(
            (intervention.metrics.completion_rate - baseline.metrics.completion_rate) * 100
        )
        staff_minutes_change.append(
            intervention.metrics.staff_minutes - baseline.metrics.staff_minutes
        )
        customer_service_incidents.append(
            float(intervention.metrics.customer_service_incidents)
        )

    modelled_daily_kwh = sum(item.power_kw() for item in project.store.equipment) * 14
    bill_daily_kwh = bill.total_kwh / 30.4
    coverage = modelled_daily_kwh / bill_daily_kwh if bill_daily_kwh else 0

    return ImpactAnalysis(
        id=f"analysis_{uuid4().hex[:12]}",
        project_id=project.id,
        scenario_id=settings.scenario_id,
        sample_count=samples,
        seed=seed,
        generated_at=datetime.now(UTC),
        bill_id=bill.id,
        metrics={
            "annual_energy_saved": _distribution(
                "Annual closing energy avoided",
                "kWh/year",
                energy_saved,
                "P10–P90 reflects equipment-load and observed behaviour uncertainty.",
            ),
            "annual_utility_savings": _distribution(
                "Annual utility savings",
                "SGD/year",
                cost_saved,
                "Uses the confirmed bill's effective tariff with a configurable uncertainty band.",
            ),
            "annual_emissions_avoided": _distribution(
                "Annual operational emissions avoided",
                "kg CO2e/year",
                emissions_avoided,
                "Operational electricity only; embodied carbon is outside this model.",
            ),
            "net_operating_impact": _distribution(
                "Net operating impact",
                "SGD/year",
                net_operating_impact,
                "Utility savings less simulated incremental overtime labour cost.",
            ),
            "profit_margin_impact": _distribution(
                "Profit-margin impact",
                "basis points",
                profit_margin_impact,
                "Net operating impact divided by the manager's assumed annual store revenue.",
            ),
            "completion_rate_change": _distribution(
                "Shutdown task completion change",
                "percentage points",
                completion_change,
                "Difference between matched baseline and Green Close simulations.",
            ),
            "staff_minutes_change": _distribution(
                "Staff effort change per close",
                "minutes/close",
                staff_minutes_change,
                "Task interaction time only; validate with a real store pilot.",
            ),
            "customer_service_incidents": _distribution(
                "Customer-service incidents",
                "incidents/close",
                customer_service_incidents,
                "Actions blocked by the Game Master are not counted as incidents.",
            ),
        },
        assumptions=[
            ImpactAssumption(
                id="tariff",
                label="Effective electricity tariff",
                value=tariff,
                unit="SGD/kWh",
                kind=EvidenceKind.DERIVED,
                source=f"Confirmed bill {bill.id}: total cost divided by total kWh",
                editable=False,
            ),
            ImpactAssumption(
                id="operating_days",
                label="Operating days per year",
                value=settings.operating_days_per_year,
                unit="days/year",
                kind=EvidenceKind.ASSUMED,
                source="Manager scenario settings",
                editable=True,
            ),
            ImpactAssumption(
                id="equipment_load",
                label="Equipment load uncertainty",
                value=settings.equipment_load_uncertainty_pct,
                unit="± percent",
                kind=EvidenceKind.ASSUMED,
                source="Demo equipment inventory pending sub-meter validation",
                editable=True,
            ),
            ImpactAssumption(
                id="annual_revenue",
                label="Annual store revenue",
                value=settings.annual_revenue_sgd,
                unit="SGD/year",
                kind=EvidenceKind.ASSUMED,
                source="Manager scenario settings; used only for margin impact",
                editable=True,
            ),
            ImpactAssumption(
                id="grid_factor",
                label="Grid emission factor",
                value=project.store.grid_emission_factor_kg_per_kwh,
                unit="kg CO2e/kWh",
                kind=EvidenceKind.ASSUMED,
                source="Demo Singapore factor; replace with the reporting-period official factor",
                editable=True,
            ),
            ImpactAssumption(
                id="behaviour",
                label="Staff and customer response",
                value="agent simulation",
                kind=EvidenceKind.SIMULATED,
                source="Matched-seed baseline and intervention runs",
                editable=False,
            ),
        ],
        risks=[
            "The bill calibrates the tariff, not individual equipment loads.",
            "Behaviour results are hypotheses until validated by an in-store pilot.",
            "Savings exclude demand charges, taxes, rebates, and equipment degradation.",
        ],
        calibration={
            "bill_daily_kwh": round(bill_daily_kwh, 2),
            "modelled_daily_kwh": round(modelled_daily_kwh, 2),
            "model_coverage_ratio": round(coverage, 3),
            "note": "Closing equipment is a bounded subsystem; it is not fitted to whole-store usage.",
        },
    )
