import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { buildStaffReplay, eventLocalMinute } from "../staffReplay";
import type { GameDay, GameDayEvent, Project, StaffProfile } from "../types";


const StaffReplayScene = lazy(() => import("./StoreScene").then((module) => ({
  default: module.StaffReplayScene,
})));


function minuteLabel(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}


function eventLabel(type: string): string {
  return type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}


export function GameDayReplay({
  project,
  gameDay,
  staff,
  events,
}: {
  project: Project;
  gameDay: GameDay;
  staff: StaffProfile[];
  events: GameDayEvent[];
}) {
  const [minute, setMinute] = useState(gameDay.start_minute);
  const [playing, setPlaying] = useState(false);
  const timedEvents = useMemo(() => events.map((event) => ({
    event,
    minute: Math.max(
      gameDay.start_minute,
      Math.min(gameDay.end_minute, eventLocalMinute(event, gameDay.timezone)),
    ),
  })), [events, gameDay.end_minute, gameDay.start_minute, gameDay.timezone]);
  const step = timedEvents.filter((item) => item.minute <= minute).length;
  const replay = useMemo(
    () => buildStaffReplay(project.store, staff, events, step),
    [events, project.store, staff, step],
  );
  const visibleEvents = timedEvents.filter((item) => item.minute <= minute).slice(-5).reverse();

  useEffect(() => {
    setMinute(gameDay.start_minute);
    setPlaying(false);
  }, [gameDay.id, gameDay.start_minute]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setMinute((current) => {
        const next = Math.min(current + 4, gameDay.end_minute);
        if (next === gameDay.end_minute) setPlaying(false);
        return next;
      });
    }, 250);
    return () => window.clearInterval(timer);
  }, [gameDay.end_minute, playing]);

  const joinedCount = Object.values(replay.activeStaff).filter(Boolean).length;
  const totalPoints = Object.values(replay.staffPoints).reduce((sum, points) => sum + points, 0);

  return (
    <section className="game-replay-panel" aria-label="Staff day replay">
      <div className="game-replay-heading">
        <div><span>04 · Recorded day</span><h2>Staff-only interaction replay</h2><p>Every movement below is reconstructed from immutable join, claim, completion, and score ledger events. Consumer agents are intentionally excluded.</p></div>
        <div><small>{joinedCount} staff visible</small><strong>{totalPoints} points</strong></div>
      </div>
      <div className="game-replay-layout">
        <div className="game-replay-stage">
          <Suspense fallback={<div className="scene-loading"><span>Loading the staff replay…</span></div>}>
            <StaffReplayScene store={project.store} staff={staff} replay={replay} />
          </Suspense>
          <div className="game-replay-clock"><span>{gameDay.local_date}</span><strong>{minuteLabel(minute)}</strong><small>{gameDay.status === "completed" ? "Final ledger" : "Live ledger"}</small></div>
        </div>
        <aside className="game-replay-events">
          <div><span>Event stream</span><strong>{step} / {events.length}</strong></div>
          {visibleEvents.map(({ event, minute: eventMinute }) => (
            <article key={event.seq}>
              <time>{minuteLabel(eventMinute)}</time>
              <p><strong>{eventLabel(event.type)}</strong><span>{event.message}</span></p>
              <small>{event.evidence_kind}</small>
            </article>
          ))}
          {!visibleEvents.length && <p className="game-empty-copy">Move the timeline forward to the first recorded staff event.</p>}
        </aside>
      </div>
      <div className="game-replay-controls">
        <button type="button" onClick={() => {
          if (minute >= gameDay.end_minute) setMinute(gameDay.start_minute);
          setPlaying((current) => !current);
        }}>{playing ? "Pause" : minute >= gameDay.end_minute ? "Replay day" : "Play day"}</button>
        <span>{minuteLabel(gameDay.start_minute)}</span>
        <input
          aria-label="Replay time"
          type="range"
          min={gameDay.start_minute}
          max={gameDay.end_minute}
          value={minute}
          onChange={(event) => { setMinute(Number(event.target.value)); setPlaying(false); }}
        />
        <span>{minuteLabel(gameDay.end_minute)}</span>
        <button type="button" onClick={() => { setMinute(gameDay.end_minute); setPlaying(false); }}>End of day</button>
      </div>
    </section>
  );
}
