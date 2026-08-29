import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { useMemo, useState } from "react";

import {
  closeGameDay,
  createGameDay,
  createTaskTemplate,
  fetchGameDayAnalysis,
  fetchGameDayEvents,
  fetchManagerLeaderboard,
  listGameDays,
  listGamePolicies,
  listStaffProfiles,
  listTaskTemplates,
  startGameDay,
} from "../api";
import type { Project, StaffRole, SustainabilityDomain, TaskTemplateCreate } from "../types";
import { GameDayReplay } from "./GameDayReplay";
import { GameLearningPanel } from "./GameLearningPanel";


function roleLabel(role: StaffRole): string {
  return role.replaceAll("_", " ");
}


export function GameControlPage({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const selectableEquipment = project.store.equipment.filter(
    (item) => item.criticality !== "protected" && (item.switchable_by_roles?.length ?? 0) > 0,
  );
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskTarget, setTaskTarget] = useState(
    selectableEquipment[0] ? `equipment:${selectableEquipment[0].id}` : "store",
  );
  const [taskDomain, setTaskDomain] = useState<SustainabilityDomain>("energy");
  const [taskLabel, setTaskLabel] = useState("Green action challenge");
  const [taskDescription, setTaskDescription] = useState("Complete this safe sustainability action during today's shift.");
  const [basePoints, setBasePoints] = useState(50);
  const days = useQuery({ queryKey: ["game-days", project.id], queryFn: () => listGameDays(project.id) });
  const templates = useQuery({ queryKey: ["task-templates", project.id], queryFn: () => listTaskTemplates(project.id) });
  const staff = useQuery({ queryKey: ["staff", project.id], queryFn: () => listStaffProfiles(project.id) });
  const currentDay = useMemo(
    () => days.data?.find((day) => day.status === "active") ?? days.data?.find((day) => day.status === "scheduled") ?? days.data?.[0],
    [days.data],
  );
  const leaderboard = useQuery({
    queryKey: ["game-leaderboard", project.id, currentDay?.id],
    queryFn: () => fetchManagerLeaderboard(project.id, currentDay!.id),
    enabled: Boolean(currentDay),
    refetchInterval: currentDay?.status === "active" ? 4000 : false,
  });
  const events = useQuery({
    queryKey: ["game-events", project.id, currentDay?.id],
    queryFn: () => fetchGameDayEvents(project.id, currentDay!.id),
    enabled: Boolean(currentDay),
    refetchInterval: currentDay?.status === "active" ? 4000 : false,
  });
  const analysis = useQuery({
    queryKey: ["game-analysis", project.id, currentDay?.id],
    queryFn: () => fetchGameDayAnalysis(project.id, currentDay!.id),
    enabled: currentDay?.status === "completed",
    retry: false,
  });
  const policies = useQuery({
    queryKey: ["game-policies", project.id],
    queryFn: () => listGamePolicies(project.id),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["game-days", project.id] });
    void queryClient.invalidateQueries({ queryKey: ["game-events", project.id] });
    void queryClient.invalidateQueries({ queryKey: ["game-leaderboard", project.id] });
    void queryClient.invalidateQueries({ queryKey: ["game-analysis", project.id] });
    void queryClient.invalidateQueries({ queryKey: ["game-policies", project.id] });
  };
  const createDayMutation = useMutation({ mutationFn: () => createGameDay(project.id), onSuccess: refresh });
  const startDayMutation = useMutation({ mutationFn: (id: string) => startGameDay(project.id, id), onSuccess: refresh });
  const closeDayMutation = useMutation({ mutationFn: (id: string) => closeGameDay(project.id, id), onSuccess: refresh });
  const createTemplateMutation = useMutation({
    mutationFn: (values: TaskTemplateCreate) => createTaskTemplate(project.id, values),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["task-templates", project.id] });
      setShowTaskForm(false);
    },
  });
  const [targetKind, targetId] = taskTarget.split(":", 2);
  const selectedEquipment = targetKind === "equipment"
    ? selectableEquipment.find((item) => item.id === targetId)
    : undefined;
  const selectedZoneId = selectedEquipment?.zone_id ?? (targetKind === "zone" ? targetId : null);
  const qrUrl = currentDay ? `${window.location.origin}/play/${currentDay.join_token}` : "";

  return (
    <section className="game-control-page" aria-label="Live staff game">
      <div className="game-control-hero">
        <div><span className="kicker">AI Game Master · live operations</span><h1>Run today’s sustainability game.</h1><p>Release only safe tasks, let staff snatch them, and record every claim, completion, and individual point award for replay.</p></div>
        <div className={`game-day-status status-${currentDay?.status ?? "none"}`}><span>Current session</span><strong>{currentDay?.status ?? "Not created"}</strong><small>{currentDay?.local_date ?? "Create today’s game day"}</small></div>
      </div>

      <div className="game-control-grid">
        <article className="game-launch-card">
          <div className="game-card-heading"><div><span>01 · Session</span><h2>Open the task market</h2></div><small>{staff.data?.filter((item) => item.active).length ?? 0} players ready</small></div>
          {!currentDay || currentDay.status === "completed" ? (
            <button className="game-primary-action" type="button" disabled={createDayMutation.isPending} onClick={() => createDayMutation.mutate()}>Create today’s game</button>
          ) : currentDay.status === "scheduled" ? (
            <button className="game-primary-action" type="button" disabled={!templates.data?.length || !staff.data?.some((item) => item.active) || startDayMutation.isPending} onClick={() => startDayMutation.mutate(currentDay.id)}>Start game and release {templates.data?.length ?? 0} tasks</button>
          ) : (
            <button className="game-close-action" type="button" disabled={closeDayMutation.isPending} onClick={() => closeDayMutation.mutate(currentDay.id)}>Close today’s game</button>
          )}
          {currentDay && currentDay.status !== "completed" && (
            <div className="game-qr-block"><QRCodeSVG value={qrUrl} size={150} bgColor="#ffffff" fgColor="#0b1711" /><div><strong>Staff join QR</strong><p>Players select their roster name and enter their private PIN.</p><input readOnly value={qrUrl} onFocus={(event) => event.target.select()} /></div></div>
          )}
        </article>

        <article className="task-pool-card">
          <div className="game-card-heading"><div><span>02 · Challenge pool</span><h2>Available task templates</h2></div><button type="button" onClick={() => setShowTaskForm(true)}>＋ New task</button></div>
          <div className="task-template-list">
            {(templates.data ?? []).map((template) => <div key={template.id}><span>{template.domain}</span><p><strong>{template.label}</strong><small>{template.zone_id ?? "Store-wide"} · {template.base_points} pts · {template.allowed_roles.map(roleLabel).join(", ")}</small></p><i>{template.verification_method.replaceAll("_", " ")}</i></div>)}
            {!templates.isLoading && !templates.data?.length && <p className="game-empty-copy">Create at least one safe challenge before starting the game.</p>}
          </div>
        </article>

        <article className="live-leaderboard-card">
          <div className="game-card-heading"><div><span>03 · Individual points</span><h2>Live leaderboard</h2></div><small>{events.data?.length ?? 0} ledger events</small></div>
          <div className="manager-leaderboard">
            {(leaderboard.data ?? []).map((entry) => <div key={entry.staff_id}><b>{String(entry.rank).padStart(2, "0")}</b><span>{entry.display_name}<small>{entry.tasks_completed} completed</small></span><strong>{entry.points} pts</strong></div>)}
            {!leaderboard.data?.length && <p className="game-empty-copy">Points appear after a player completes a claimed task.</p>}
          </div>
        </article>
      </div>

      {currentDay && (
        <GameDayReplay
          project={project}
          gameDay={currentDay}
          staff={staff.data ?? []}
          events={events.data ?? []}
        />
      )}

      {currentDay?.status === "completed" && (
        <GameLearningPanel
          analysis={analysis.data}
          policy={policies.data?.find((policy) => policy.version === analysis.data?.learned_policy_version)}
          loading={analysis.isLoading}
        />
      )}

      {showTaskForm && (
        <div className="modal-backdrop" role="presentation">
          <section className="task-create-modal" role="dialog" aria-modal="true" aria-labelledby="task-create-title">
            <button className="modal-close" type="button" aria-label="Close" onClick={() => setShowTaskForm(false)}>×</button>
            <span className="kicker">Safe challenge template</span><h2 id="task-create-title">Add task to the pool</h2>
            <form onSubmit={(event) => {
              event.preventDefault();
              createTemplateMutation.mutate({
                label: taskLabel,
                description: taskDescription,
                domain: taskDomain,
                zone_id: selectedZoneId,
                equipment_id: selectedEquipment?.id ?? null,
                allowed_roles: selectedEquipment?.switchable_by_roles ?? ["manager", "closing_associate", "cashier"],
                allowed_staff_ids: [],
                available_from_minute: 0,
                available_until_minute: 1440,
                expected_minutes: 5,
                base_points: basePoints,
                maximum_points: Math.max(basePoints + 10, basePoints),
                verification_method: "self_confirmation",
                estimated_impact_value: null,
                estimated_impact_unit: null,
              });
            }}>
              <label><span>Task name</span><input required minLength={3} value={taskLabel} onChange={(event) => setTaskLabel(event.target.value)} /></label>
              <label><span>Staff instruction</span><textarea required minLength={3} value={taskDescription} onChange={(event) => setTaskDescription(event.target.value)} /></label>
              <label><span>Sustainability domain</span><select value={taskDomain} onChange={(event) => setTaskDomain(event.target.value as SustainabilityDomain)}><option value="energy">Energy</option><option value="water">Water</option><option value="waste">Waste</option><option value="food">Food</option><option value="transport">Transport</option><option value="buying">Buying</option></select></label>
              <label><span>Safe task target</span><select value={taskTarget} onChange={(event) => setTaskTarget(event.target.value)}><option value="store">Store-wide</option><optgroup label="Zones">{project.store.zones.map((zone) => <option key={zone.id} value={`zone:${zone.id}`}>{zone.label} (zone)</option>)}</optgroup>{selectableEquipment.length > 0 && <optgroup label="Authorized equipment">{selectableEquipment.map((item) => <option key={item.id} value={`equipment:${item.id}`}>{item.label}</option>)}</optgroup>}</select></label>
              <label><span>Base individual points</span><input type="number" min="1" max="10000" value={basePoints} onChange={(event) => setBasePoints(Number(event.target.value))} /></label>
              <p className="game-safety-callout"><strong>Game Master boundary</strong> Protected loads never appear as targets. Equipment challenges inherit authoritative role and zone permissions; zone and store-wide habits remain limited to configured staff roles.</p>
              {createTemplateMutation.isError && <p className="form-error">{createTemplateMutation.error.message}</p>}
              <div className="run-create-actions"><button type="button" onClick={() => setShowTaskForm(false)}>Cancel</button><button className="primary" type="submit" disabled={createTemplateMutation.isPending}>Add challenge</button></div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
