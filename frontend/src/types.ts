export type Position = { x: number; z: number };

export type Zone = {
  id: string;
  label: string;
  center: Position;
  width: number;
  depth: number;
};

export type EquipmentState = "on" | "standby" | "off";

export type Equipment = {
  id: string;
  label: string;
  zone_id: string;
  position: Position;
  state: EquipmentState;
  power_kw_by_state: Record<EquipmentState, number>;
  criticality: "non_critical" | "operational" | "protected";
  customer_facing: boolean;
};

export type StaffAgent = {
  id: string;
  label: string;
  role: "manager" | "closing_associate" | "cashier";
  zone_id: string;
  position: Position;
  checklist_completed: boolean;
  shift_ended: boolean;
};

export type CustomerAgent = {
  id: string;
  label: string;
  segment: "browser" | "mission_shopper" | "value_seeker";
  zone_id: string;
  position: Position;
  active: boolean;
  satisfaction: number;
};

export type Store = {
  id: string;
  name: string;
  timezone: string;
  floor_area_m2: number;
  opening_minute: number;
  closing_minute: number;
  zones: Zone[];
  equipment: Equipment[];
  agents: StaffAgent[];
  customers: CustomerAgent[];
  tariff_sgd_per_kwh: number;
  grid_emission_factor_kg_per_kwh: number;
};

export type SimulationEvent = {
  seq: number;
  at_minute: number;
  type: string;
  message: string;
  agent_id: string | null;
  target_id: string | null;
  data: Record<string, unknown>;
};

export type AgentMode = "deterministic" | "openai" | "ollama";

export type AgentProposalAction =
  | "move"
  | "operate_equipment"
  | "assist_customer"
  | "remind_staff"
  | "wait"
  | "exit";

export type AgentProposal = {
  action: AgentProposalAction;
  target_id: string | null;
  destination: string | null;
  public_reason: string;
  confidence: number;
};

export type AgentDecisionAudit = {
  event_seq: number | null;
  at_minute: number;
  scenario_id: string;
  actor_kind: "staff" | "consumer";
  agent_id: string;
  observation: Record<string, unknown>;
  proposal: AgentProposal;
  accepted: boolean;
  outcome: string;
  provider: string;
  model: string;
  generated_by_ai: boolean;
  fallback_used: boolean;
  failure_kind: string | null;
  public_reason: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  memory_summary: string;
};

export type AgentUsageSummary = {
  provider_calls: number;
  deterministic_decisions: number;
  cached_decisions: number;
  fallback_decisions: number;
  provider_failures: number;
  budget_exhaustions: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  total_latency_ms: number;
};

export type AgentIntelligenceSettings = {
  mode: AgentMode;
  model: string | null;
  max_calls: number;
  max_calls_per_agent: number;
  timeout_seconds: number;
  max_concurrency: number;
  token_budget: number;
  cost_budget_usd: number;
};

export type SimulationRunCreate = AgentIntelligenceSettings & {
  seed: number;
  sample_count: number;
};

export type RunMetrics = {
  total_kwh: number;
  after_hours_kwh: number;
  cost_sgd: number;
  emissions_kg_co2: number;
  shutdown_tasks_total: number;
  shutdown_tasks_completed: number;
  completion_rate: number;
  staff_minutes: number;
  overtime_minutes: number;
  rejected_actions: number;
  customer_service_incidents: number;
};

export type SimulationRun = {
  id: string;
  scenario_id: string;
  seed: number;
  store: Store;
  events: SimulationEvent[];
  metrics: RunMetrics;
  agent_decisions: AgentDecisionAudit[];
  provider_usage: AgentUsageSummary;
};

export type ComparisonMetric = {
  baseline: number;
  intervention: number;
  difference: number;
  percent_change: number | null;
};

export type ScenarioComparison = {
  baseline_run: SimulationRun;
  intervention_run: SimulationRun;
  energy_kwh: ComparisonMetric;
  cost_sgd: ComparisonMetric;
  emissions_kg_co2: ComparisonMetric;
  completion_rate: ComparisonMetric;
};

export type ScenarioSettings = {
  scenario_id: "green-close";
  operating_days_per_year: number;
  labour_cost_sgd_per_hour: number;
  annual_revenue_sgd: number;
  equipment_load_uncertainty_pct: number;
  tariff_uncertainty_pct: number;
  adoption_rate: number;
};

export type StoreSettings = Pick<
  Store,
  | "name"
  | "timezone"
  | "floor_area_m2"
  | "opening_minute"
  | "closing_minute"
  | "tariff_sgd_per_kwh"
  | "grid_emission_factor_kg_per_kwh"
>;

export type Project = {
  id: string;
  name: string;
  store: Store;
  settings: ScenarioSettings;
  agent_settings: AgentIntelligenceSettings;
  created_at: string;
  updated_at: string;
};

export type UtilityBill = {
  id: string;
  project_id: string;
  filename: string;
  period_start: string;
  period_end: string;
  total_kwh: number;
  total_cost_sgd: number;
  average_tariff_sgd_per_kwh: number;
  status: "needs_confirmation" | "confirmed";
  raw_file_retained: boolean;
};

export type DemoBundle = { project: Project; bills: UtilityBill[] };

export type Distribution = {
  label: string;
  unit: string;
  p10: number;
  p50: number;
  p90: number;
  mean: number;
  evidence_kind: "measured" | "derived" | "assumed" | "simulated";
  interpretation: string;
};

export type ImpactAnalysis = {
  id: string;
  project_id: string;
  scenario_id: string;
  sample_count: number;
  seed: number;
  metrics: Record<string, Distribution>;
  assumptions: Array<{
    id: string;
    label: string;
    value: number | string;
    unit: string | null;
    kind: "measured" | "derived" | "assumed" | "simulated";
    source: string;
    editable: boolean;
  }>;
  risks: string[];
  calibration: {
    bill_daily_kwh: number;
    modelled_daily_kwh: number;
    model_coverage_ratio: number;
    note: string;
  };
};

export type SimulationRunStatus = "queued" | "running" | "completed" | "failed";

export type SimulationRunSummary = {
  id: string;
  project_id: string;
  created_at: string;
  completed_at: string | null;
  status: SimulationRunStatus;
  seed: number;
  sample_count: number;
  estimated_savings_sgd: number | null;
  configuration_current: boolean;
  game_master_rules_version: string;
  agent_mode: AgentMode;
  agent_provider: string;
  agent_model: string;
  fallback_decisions: number;
  provider_calls: number;
  total_tokens: number;
  estimated_cost_usd: number;
  failure_message: string | null;
};

export type PersistedSimulationRun = {
  id: string;
  project_id: string;
  created_at: string;
  completed_at: string | null;
  status: SimulationRunStatus;
  seed: number;
  sample_count: number;
  comparison: ScenarioComparison | null;
  impact_analysis: ImpactAnalysis | null;
  store_snapshot: Store;
  scenario_settings_snapshot: ScenarioSettings;
  evidence_snapshot: UtilityBill | null;
  baseline_explanations: EventExplanation[];
  intervention_explanations: EventExplanation[];
  configuration_hash: string;
  configuration_current: boolean;
  game_master_rules_version: string;
  game_master_rules_snapshot: Array<{
    id: string;
    label: string;
    description: string;
  }>;
  agent_mode: AgentMode;
  agent_provider: string;
  agent_model: string;
  provider_configuration_fingerprint: string;
  prompt_template_version: string;
  agent_settings_snapshot: AgentIntelligenceSettings;
  agent_usage: AgentUsageSummary;
  failure_message: string | null;
};

export type ProviderModeStatus = {
  mode: AgentMode;
  provider: string;
  available: boolean;
  configured: boolean;
  model: string | null;
  detail: string;
};

export type AIStatus = {
  modes: ProviderModeStatus[];
  selected_mode: AgentMode;
  prompt_template_version: string;
  credentials_exposed: false;
};

export type AITestResult = {
  success: boolean;
  mode: AgentMode;
  provider: string;
  model: string;
  latency_ms: number;
  proposal: AgentProposal | null;
  error: string | null;
};

export type EventExplanation = {
  event_seq: number;
  summary: string;
  rationale: string;
  rules_checked: string[];
  grounded_in: string[];
  counterfactual: string;
  confidence: "high" | "medium";
};

export type ChecklistTask = {
  id: string;
  equipment_id: string;
  label: string;
  zone_label: string;
  assigned_role: string;
  criticality: string;
  completed_at: string | null;
};

export type ChecklistSession = {
  id: string;
  token: string;
  project_id: string;
  store_name: string;
  scenario_label: string;
  status: "open" | "completed";
  tasks: ChecklistTask[];
  safety_note: string;
  created_at: string;
  expires_at: string;
};

export type WorldState = {
  staffPositions: Record<string, Position>;
  customerPositions: Record<string, Position>;
  activeCustomers: Record<string, boolean>;
  equipmentStates: Record<string, EquipmentState>;
  customerCount: number;
};
