import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { updateStoreSettings } from "../api";
import type {
  DemoBundle,
  ImpactAnalysis,
  Project,
  StoreSettings as StoreSettingsValues,
  UtilityBill,
} from "../types";
import { BillUpload } from "./BillUpload";
import { ScenarioSettings } from "./ScenarioSettings";

function minuteToTime(minute: number): string {
  const hours = Math.floor(minute / 60).toString().padStart(2, "0");
  const minutes = (minute % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

function timeToMinute(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function storeSettings(project: Project): StoreSettingsValues {
  const { store } = project;
  return {
    name: store.name,
    timezone: store.timezone,
    floor_area_m2: store.floor_area_m2,
    opening_minute: store.opening_minute,
    closing_minute: store.closing_minute,
    tariff_sgd_per_kwh: store.tariff_sgd_per_kwh,
    grid_emission_factor_kg_per_kwh: store.grid_emission_factor_kg_per_kwh,
  };
}

function StoreProfile({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<StoreSettingsValues>(() => storeSettings(project));
  useEffect(() => setValues(storeSettings(project)), [project]);

  const save = useMutation({
    mutationFn: () => updateStoreSettings(project.id, values),
    onSuccess: (updated) => {
      queryClient.setQueryData<DemoBundle>(["demo"], (current) => (
        current ? { ...current, project: updated } : current
      ));
      void queryClient.invalidateQueries({ queryKey: ["comparison"] });
      void queryClient.invalidateQueries({ queryKey: ["explanations"] });
      void queryClient.invalidateQueries({ queryKey: ["analysis"] });
    },
  });

  return (
    <section className="config-card store-profile-card">
      <div className="config-card-heading">
        <div><span>01 · Store profile</span><h2>Operating context</h2></div>
        <small>Feeds the simulation model</small>
      </div>
      <form className="config-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <label className="field-wide">
          <span>Store name</span>
          <input
            required
            maxLength={120}
            value={values.name}
            onChange={(event) => setValues({ ...values, name: event.target.value })}
          />
        </label>
        <label>
          <span>Timezone</span>
          <select value={values.timezone} onChange={(event) => setValues({ ...values, timezone: event.target.value })}>
            <option value="Asia/Singapore">Asia / Singapore</option>
            <option value="Asia/Kuala_Lumpur">Asia / Kuala Lumpur</option>
            <option value="Asia/Hong_Kong">Asia / Hong Kong</option>
            <option value="Australia/Sydney">Australia / Sydney</option>
          </select>
        </label>
        <label>
          <span>Floor area (m²)</span>
          <input type="number" min="1" step="1" value={values.floor_area_m2} onChange={(event) => setValues({ ...values, floor_area_m2: Number(event.target.value) })} />
        </label>
        <label>
          <span>Opening time</span>
          <input type="time" value={minuteToTime(values.opening_minute)} onChange={(event) => setValues({ ...values, opening_minute: timeToMinute(event.target.value) })} />
        </label>
        <label>
          <span>Closing time</span>
          <input type="time" value={minuteToTime(values.closing_minute)} onChange={(event) => setValues({ ...values, closing_minute: timeToMinute(event.target.value) })} />
        </label>
        <label>
          <span>Electricity tariff (S$/kWh)</span>
          <input type="number" min="0.0001" max="100" step="0.0001" value={values.tariff_sgd_per_kwh} onChange={(event) => setValues({ ...values, tariff_sgd_per_kwh: Number(event.target.value) })} />
        </label>
        <label>
          <span>Grid emissions (kg CO₂e/kWh)</span>
          <input type="number" min="0" max="10" step="0.001" value={values.grid_emission_factor_kg_per_kwh} onChange={(event) => setValues({ ...values, grid_emission_factor_kg_per_kwh: Number(event.target.value) })} />
        </label>
        <div className="config-form-actions">
          <span className={save.isError ? "save-state error" : "save-state"}>
            {save.isError ? save.error.message : save.isSuccess ? "Saved · simulation refreshed" : "Changes are versioned with this project"}
          </span>
          <button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save store profile"}</button>
        </div>
      </form>
      <div className="model-inventory" aria-label="Simulation inventory">
        <span><b>{project.store.zones.length}</b> zones</span>
        <span><b>{project.store.equipment.length}</b> monitored loads</span>
        <span><b>{project.store.agents.length}</b> staff agents</span>
        <span><b>{project.store.customers.length}</b> consumer profiles</span>
      </div>
    </section>
  );
}

function DocumentLibrary({
  project,
  bills,
  onConfirmed,
}: {
  project: Project;
  bills: UtilityBill[];
  onConfirmed: (bill: UtilityBill) => void;
}) {
  return (
    <section className="config-card documents-card">
      <div className="config-card-heading">
        <div><span>03 · Evidence documents</span><h2>Utility bill library</h2></div>
        <small>{bills.length} source{bills.length === 1 ? "" : "s"} · raw files discarded</small>
      </div>
      <div className="documents-layout">
        <div className="document-list">
          {bills.map((bill) => (
            <article key={bill.id}>
              <span className="document-file-icon">kWh</span>
              <div>
                <strong>{bill.filename.replace("uploaded_utility_bill", "Utility bill")}</strong>
                <small>{bill.period_start} — {bill.period_end} · {bill.total_kwh.toLocaleString()} kWh</small>
              </div>
              <span className={`document-status ${bill.status}`}>{bill.status.replace("_", " ")}</span>
            </article>
          ))}
        </div>
        <div className="document-upload-surface">
          <BillUpload projectId={project.id} onConfirmed={onConfirmed} />
          <p><i>⌁</i><span><strong>Private by default</strong>Only confirmed fields enter the model. Original documents are parsed in memory and never retained.</span></p>
        </div>
      </div>
    </section>
  );
}

export function ConfigurationPage({
  project,
  bills,
  analysis,
  onConfirmed,
}: {
  project: Project;
  bills: UtilityBill[];
  analysis?: ImpactAnalysis;
  onConfirmed: (bill: UtilityBill) => void;
}) {
  const uniqueBills = useMemo(
    () => Array.from(new Map(bills.map((bill) => [bill.id, bill])).values()),
    [bills],
  );

  return (
    <section className="configuration-page" aria-label="Project configuration">
      <div className="configuration-intro">
        <div>
          <span className="kicker">Project control plane</span>
          <h1>Ground the simulation in your store.</h1>
          <p>Manage operating context, behavioural assumptions, and source documents in one place. Saved changes automatically refresh the comparison model.</p>
        </div>
        <div className="configuration-health">
          <span>Model readiness</span>
          <strong>{uniqueBills.some((bill) => bill.status === "confirmed") ? "Ready" : "Needs evidence"}</strong>
          <small><i /> {analysis ? `${Math.round(analysis.calibration.model_coverage_ratio * 100)}% model coverage` : "Analysis refreshing"}</small>
        </div>
      </div>

      <div className="configuration-grid">
        <StoreProfile project={project} />
        <ScenarioSettings project={project} />
        <DocumentLibrary project={project} bills={uniqueBills} onConfirmed={onConfirmed} />
      </div>
    </section>
  );
}
