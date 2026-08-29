import type {
  DemoBundle,
  ChecklistSession,
  EventExplanation,
  ImpactAnalysis,
  PersistedSimulationRun,
  Project,
  ScenarioSettings,
  ScenarioComparison,
  Store,
  StoreSettings,
  SimulationRunSummary,
  UtilityBill,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function bootstrapDemo(): Promise<DemoBundle> {
  return request("/api/demo/bootstrap", { method: "POST" });
}

export function fetchStore(): Promise<Store> {
  return request("/api/demo/store");
}

export function fetchComparison(seed: number, projectId?: string): Promise<ScenarioComparison> {
  const project = projectId ? `&project_id=${encodeURIComponent(projectId)}` : "";
  return request(`/api/simulations/compare?seed=${seed}${project}`);
}

export function runAnalysis(projectId: string, seed: number): Promise<ImpactAnalysis> {
  return request(`/api/projects/${projectId}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ samples: 120, seed }),
  });
}

export function fetchExplanations(
  scenarioId: "baseline" | "green-close",
  seed: number,
  projectId?: string,
): Promise<EventExplanation[]> {
  const project = projectId ? `&project_id=${encodeURIComponent(projectId)}` : "";
  return request(`/api/simulations/explanations?scenario_id=${scenarioId}&seed=${seed}${project}`);
}

export function createStaffChecklist(projectId: string): Promise<ChecklistSession> {
  return request(`/api/projects/${projectId}/checklists`, { method: "POST" });
}

export function fetchChecklist(token: string): Promise<ChecklistSession> {
  return request(`/api/checklists/${token}`);
}

export function completeChecklistTask(token: string, taskId: string): Promise<ChecklistSession> {
  return request(`/api/checklists/${token}/tasks/${taskId}/complete`, { method: "POST" });
}

export function updateScenarioSettings(
  projectId: string,
  settings: ScenarioSettings,
): Promise<Project> {
  return request(`/api/projects/${projectId}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function updateStoreSettings(
  projectId: string,
  settings: StoreSettings,
): Promise<Project> {
  return request(`/api/projects/${projectId}/store`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function listSimulationRuns(projectId: string): Promise<SimulationRunSummary[]> {
  return request(`/api/projects/${projectId}/runs`);
}

export function fetchSimulationRun(
  projectId: string,
  runId: string,
): Promise<PersistedSimulationRun> {
  return request(`/api/projects/${projectId}/runs/${runId}`);
}

export function createSimulationRun(
  projectId: string,
  values: { seed: number; sample_count: number },
): Promise<PersistedSimulationRun> {
  return request(`/api/projects/${projectId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function uploadUtilityBill(projectId: string, file: File): Promise<UtilityBill> {
  const body = new FormData();
  body.append("bill_file", file);
  return request(`/api/projects/${projectId}/bills/upload`, { method: "POST", body });
}

export function confirmUtilityBill(
  projectId: string,
  billId: string,
  values: Pick<UtilityBill, "period_start" | "period_end" | "total_kwh" | "total_cost_sgd">,
): Promise<UtilityBill> {
  return request(`/api/projects/${projectId}/bills/${billId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export async function downloadDecisionBrief(projectId: string, analysisId: string): Promise<string> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/analyses/${analysisId}/report.md`,
  );
  if (!response.ok) throw new Error("Decision brief could not be generated");
  return response.text();
}

export async function downloadRunDecisionBrief(projectId: string, runId: string): Promise<string> {
  const response = await fetch(`${API_URL}/api/projects/${projectId}/runs/${runId}/report.md`);
  if (!response.ok) throw new Error("Decision brief could not be generated");
  return response.text();
}
