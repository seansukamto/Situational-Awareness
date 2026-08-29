import type {
  AIStatus,
  AITestResult,
  AgentIntelligenceSettings,
  AgentMode,
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
  SimulationRunCreate,
  UtilityBill,
  AvatarDefinition,
  GameDay,
  GameDayEvent,
  GameJoinResponse,
  GameJoinSummary,
  LeaderboardEntry,
  StaffProfile,
  StaffProfileCreate,
  TaskInstance,
  TaskTemplate,
  TaskTemplateCreate,
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

export function updateAgentSettings(
  projectId: string,
  settings: AgentIntelligenceSettings,
): Promise<Project> {
  return request(`/api/projects/${projectId}/agent-settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function fetchAIStatus(): Promise<AIStatus> {
  return request("/api/ai/status");
}

export function testAIProvider(values: {
  mode: AgentMode;
  model: string | null;
  timeout_seconds: number;
}): Promise<AITestResult> {
  return request("/api/ai/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
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
  values: SimulationRunCreate,
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

export function listAvatars(): Promise<AvatarDefinition[]> {
  return request("/api/avatars");
}

export function listStaffProfiles(projectId: string): Promise<StaffProfile[]> {
  return request(`/api/projects/${projectId}/staff`);
}

export function createStaffProfile(
  projectId: string,
  values: StaffProfileCreate,
): Promise<StaffProfile> {
  return request(`/api/projects/${projectId}/staff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function updateStaffProfile(
  projectId: string,
  staffId: string,
  values: Partial<Omit<StaffProfile, "id" | "project_id" | "created_at" | "updated_at">>,
): Promise<StaffProfile> {
  return request(`/api/projects/${projectId}/staff/${staffId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function resetStaffPin(
  projectId: string,
  staffId: string,
  joinPin: string,
): Promise<StaffProfile> {
  return request(`/api/projects/${projectId}/staff/${staffId}/reset-pin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ join_pin: joinPin }),
  });
}

export function listTaskTemplates(projectId: string): Promise<TaskTemplate[]> {
  return request(`/api/projects/${projectId}/task-templates`);
}

export function createTaskTemplate(
  projectId: string,
  values: TaskTemplateCreate,
): Promise<TaskTemplate> {
  return request(`/api/projects/${projectId}/task-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function listGameDays(projectId: string): Promise<GameDay[]> {
  return request(`/api/projects/${projectId}/game-days`);
}

export function createGameDay(projectId: string): Promise<GameDay> {
  return request(`/api/projects/${projectId}/game-days`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function startGameDay(projectId: string, gameDayId: string): Promise<GameDay> {
  return request(`/api/projects/${projectId}/game-days/${gameDayId}/start`, {
    method: "POST",
  });
}

export function closeGameDay(projectId: string, gameDayId: string): Promise<GameDay> {
  return request(`/api/projects/${projectId}/game-days/${gameDayId}/close`, {
    method: "POST",
  });
}

export function fetchGameDayEvents(
  projectId: string,
  gameDayId: string,
): Promise<GameDayEvent[]> {
  return request(`/api/projects/${projectId}/game-days/${gameDayId}/events`);
}

export function fetchManagerLeaderboard(
  projectId: string,
  gameDayId: string,
): Promise<LeaderboardEntry[]> {
  return request(`/api/projects/${projectId}/game-days/${gameDayId}/leaderboard`);
}

export function inspectGameJoin(joinToken: string): Promise<GameJoinSummary> {
  return request(`/api/game/join/${joinToken}`);
}

export function joinStaffGame(
  joinToken: string,
  staffId: string,
  joinPin: string,
): Promise<GameJoinResponse> {
  return request(`/api/game/join/${joinToken}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ staff_id: staffId, join_pin: joinPin }),
  });
}

function gameRequest<T>(path: string, sessionToken: string, init?: RequestInit): Promise<T> {
  return request(path, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${sessionToken}`,
    },
  });
}

export function listGameTasks(sessionToken: string): Promise<TaskInstance[]> {
  return gameRequest("/api/game/tasks", sessionToken);
}

export function claimGameTask(sessionToken: string, taskId: string): Promise<TaskInstance> {
  return gameRequest(`/api/game/tasks/${taskId}/claim`, sessionToken, { method: "POST" });
}

export function releaseGameTask(sessionToken: string, taskId: string): Promise<TaskInstance> {
  return gameRequest(`/api/game/tasks/${taskId}/release`, sessionToken, { method: "POST" });
}

export function completeGameTask(sessionToken: string, taskId: string): Promise<TaskInstance> {
  return gameRequest(`/api/game/tasks/${taskId}/complete`, sessionToken, { method: "POST" });
}

export function fetchStaffLeaderboard(sessionToken: string): Promise<LeaderboardEntry[]> {
  return gameRequest("/api/game/leaderboard", sessionToken);
}
