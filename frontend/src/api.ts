import type {
  DemoBundle,
  ImpactAnalysis,
  ScenarioComparison,
  Store,
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

export function fetchComparison(seed: number): Promise<ScenarioComparison> {
  return request(`/api/simulations/compare?seed=${seed}`);
}

export function runAnalysis(projectId: string, seed: number): Promise<ImpactAnalysis> {
  return request(`/api/projects/${projectId}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ samples: 120, seed }),
  });
}
