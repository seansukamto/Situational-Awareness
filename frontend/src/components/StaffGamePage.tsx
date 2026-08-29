import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  claimGameTask,
  completeGameTask,
  fetchStaffLeaderboard,
  inspectGameJoin,
  joinStaffGame,
  listGameTasks,
  releaseGameTask,
} from "../api";
import type { GameJoinResponse, TaskInstance } from "../types";


function sessionKey(joinToken: string): string {
  return `sa-game-session:${joinToken}`;
}


function readSession(joinToken: string): GameJoinResponse | null {
  try {
    const value = window.sessionStorage.getItem(sessionKey(joinToken));
    return value ? JSON.parse(value) as GameJoinResponse : null;
  } catch {
    return null;
  }
}


function taskImpact(task: TaskInstance): string {
  return task.estimated_impact_value == null
    ? "Impact estimated after completion"
    : `${task.estimated_impact_value} ${task.estimated_impact_unit ?? "impact"}`;
}


export function StaffGamePage({ joinToken }: { joinToken: string }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<GameJoinResponse | null>(() => readSession(joinToken));
  const [staffId, setStaffId] = useState("");
  const [pin, setPin] = useState("");
  const joinSummary = useQuery({
    queryKey: ["game-join", joinToken],
    queryFn: () => inspectGameJoin(joinToken),
    retry: false,
  });
  useEffect(() => {
    if (!staffId && joinSummary.data?.staff[0]) setStaffId(joinSummary.data.staff[0].id);
  }, [joinSummary.data, staffId]);
  const join = useMutation({
    mutationFn: () => joinStaffGame(joinToken, staffId, pin),
    onSuccess: (joined) => {
      window.sessionStorage.setItem(sessionKey(joinToken), JSON.stringify(joined));
      setSession(joined);
      setPin("");
    },
  });
  const tasks = useQuery({
    queryKey: ["staff-game-tasks", session?.game_day.id, session?.staff.id],
    queryFn: () => listGameTasks(session!.session_token),
    enabled: Boolean(session),
    refetchInterval: session?.game_day.status === "active" ? 4000 : false,
    retry: false,
  });
  const leaderboard = useQuery({
    queryKey: ["staff-game-leaderboard", session?.game_day.id],
    queryFn: () => fetchStaffLeaderboard(session!.session_token),
    enabled: Boolean(session),
    refetchInterval: session?.game_day.status === "active" ? 4000 : false,
    retry: false,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["staff-game-tasks"] });
    void queryClient.invalidateQueries({ queryKey: ["staff-game-leaderboard"] });
  };
  const claim = useMutation({ mutationFn: (taskId: string) => claimGameTask(session!.session_token, taskId), onSuccess: refresh });
  const release = useMutation({ mutationFn: (taskId: string) => releaseGameTask(session!.session_token, taskId), onSuccess: refresh });
  const complete = useMutation({ mutationFn: (taskId: string) => completeGameTask(session!.session_token, taskId), onSuccess: refresh });
  const available = useMemo(() => (tasks.data ?? []).filter((task) => task.status === "available"), [tasks.data]);
  const mine = useMemo(() => (tasks.data ?? []).filter((task) => task.status === "claimed"), [tasks.data]);
  const completed = useMemo(() => (tasks.data ?? []).filter((task) => task.status === "completed"), [tasks.data]);
  const myLeaderboard = leaderboard.data?.find((entry) => entry.staff_id === session?.staff.id);

  if (joinSummary.isLoading) {
    return <main className="staff-game-shell staff-game-loading">Opening today’s sustainability game…</main>;
  }
  if (joinSummary.isError || !joinSummary.data) {
    return <main className="staff-game-shell staff-game-error"><span className="brand-mark">SA</span><h1>Game link unavailable</h1><p>{joinSummary.error?.message ?? "Ask your manager for a new QR code."}</p></main>;
  }
  if (!session) {
    return (
      <main className="staff-game-shell join-game-shell">
        <header className="staff-game-header"><div className="side-brand"><span className="brand-mark">SA</span><div><strong>Situational</strong><span>Awareness</span></div></div><span>Staff game</span></header>
        <section className="join-game-card">
          <span className="kicker">{joinSummary.data.local_date}</span>
          <h1>Join {joinSummary.data.store_name}.</h1>
          <p>Pick your configured player profile, enter your PIN, and snatch safe sustainability challenges for individual points.</p>
          <form onSubmit={(event) => { event.preventDefault(); join.mutate(); }}>
            <label><span>Your player profile</span><select required value={staffId} onChange={(event) => setStaffId(event.target.value)}>{joinSummary.data.staff.map((staff) => <option key={staff.id} value={staff.id}>{staff.display_name} · {staff.role.replaceAll("_", " ")}</option>)}</select></label>
            <label><span>Private join PIN</span><input required type="password" inputMode="numeric" pattern="[0-9]{4,8}" value={pin} onChange={(event) => setPin(event.target.value)} /></label>
            {join.isError && <p className="form-error">{join.error.message}</p>}
            <button type="submit" disabled={!staffId || join.isPending}>{join.isPending ? "Joining…" : "Enter the game"}</button>
          </form>
          <aside><strong>Safe by design</strong><p>The Game Master shows only tasks allowed for your role, zone, and equipment permissions.</p></aside>
        </section>
      </main>
    );
  }

  return (
    <main className="staff-game-shell live-staff-game">
      <header className="staff-game-header">
        <div className="side-brand"><span className="brand-mark">SA</span><div><strong>Situational</strong><span>Awareness</span></div></div>
        <button type="button" onClick={() => { window.sessionStorage.removeItem(sessionKey(joinToken)); setSession(null); }}>Leave</button>
      </header>
      <section className="player-score-hero">
        <div className={`player-avatar avatar-${session.staff.avatar_id}`}>{session.staff.display_name.slice(0, 1).toUpperCase()}<small>3D</small></div>
        <div><span>Playing as</span><h1>{session.staff.display_name}</h1><p>{session.staff.role.replaceAll("_", " ")} · {session.game_day.status} session</p></div>
        <div className="player-score"><span>Individual score</span><strong>{myLeaderboard?.points ?? 0}</strong><small>{myLeaderboard?.tasks_completed ?? 0} tasks complete</small></div>
      </section>

      {(claim.isError || release.isError || complete.isError || tasks.isError) && (
        <p className="staff-game-action-error">{claim.error?.message ?? release.error?.message ?? complete.error?.message ?? tasks.error?.message}</p>
      )}

      <section className="staff-task-section">
        <div className="staff-task-heading"><div><span>Task market</span><h2>Available to snatch</h2></div><b>{available.length}</b></div>
        <div className="staff-task-list">
          {available.map((task) => <article className={`staff-task-card available ${task.game_master_recommended ? "recommended" : ""}`} key={task.id}>{task.game_master_recommended && <aside><strong>✦ Game Master pick</strong><span>{task.recommendation_reason}</span></aside>}<div><span>{task.domain}</span><strong>{task.base_points} pts</strong></div><h3>{task.label}</h3><p>{task.description}</p><footer><small>{task.zone_id?.replaceAll("_", " ") ?? "Store-wide"} · {taskImpact(task)}</small><button type="button" disabled={claim.isPending} onClick={() => claim.mutate(task.id)}>Snatch task</button></footer></article>)}
          {!available.length && <p className="staff-game-empty">No eligible tasks are available right now. Claimed tasks stay reserved for their player.</p>}
        </div>
      </section>

      <section className="staff-task-section claimed-section">
        <div className="staff-task-heading"><div><span>In progress</span><h2>My claimed tasks</h2></div><b>{mine.length}</b></div>
        <div className="staff-task-list">
          {mine.map((task) => <article className="staff-task-card claimed" key={task.id}><div><span>Reserved for you</span><strong>{task.base_points} pts</strong></div><h3>{task.label}</h3><p>{task.description}</p><footer><button className="release-task" type="button" disabled={release.isPending || complete.isPending} onClick={() => release.mutate(task.id)}>Release</button><button type="button" disabled={complete.isPending} onClick={() => complete.mutate(task.id)}>Complete + points</button></footer></article>)}
          {!mine.length && <p className="staff-game-empty">Snatch a task from the market to begin.</p>}
        </div>
      </section>

      <section className="staff-leaderboard-section">
        <div className="staff-task-heading"><div><span>Live ranking</span><h2>Individual leaderboard</h2></div><b>{leaderboard.data?.length ?? 0}</b></div>
        <div className="staff-live-leaderboard">
          {(leaderboard.data ?? []).map((entry) => <div className={entry.staff_id === session.staff.id ? "current" : ""} key={entry.staff_id}><b>{String(entry.rank).padStart(2, "0")}</b><span>{entry.display_name}<small>{entry.tasks_completed} completed</small></span><strong>{entry.points} pts</strong></div>)}
          {!leaderboard.data?.length && <p className="staff-game-empty">The first verified completion takes the lead.</p>}
        </div>
      </section>

      {completed.length > 0 && <section className="staff-completed-strip"><span>Completed today</span>{completed.map((task) => <div key={task.id}><strong>✓ {task.label}</strong><small>+{task.points_awarded} points</small></div>)}</section>}
    </main>
  );
}
