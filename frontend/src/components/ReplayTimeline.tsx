import { useEffect } from "react";

import type { SimulationEvent } from "../types";

function formatTime(minute: number): string {
  const hours = Math.floor(minute / 60) % 24;
  const minutes = minute % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function ReplayTimeline({
  events,
  step,
  setStep,
  playing,
  setPlaying,
}: {
  events: SimulationEvent[];
  step: number;
  setStep: (step: number) => void;
  playing: boolean;
  setPlaying: (playing: boolean) => void;
}) {
  useEffect(() => {
    if (!playing) return;
    if (step >= events.length) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStep(step + 1), 900);
    return () => window.clearTimeout(timer);
  }, [events.length, playing, setPlaying, setStep, step]);

  const current = step > 0 ? events[step - 1] : null;
  const percentage = events.length ? (step / events.length) * 100 : 0;
  return (
    <section className="replay-panel" aria-label="Simulation replay controls">
      <div className="replay-toolbar">
        <button
          className="play-button"
          type="button"
          onClick={() => {
            if (step >= events.length) setStep(0);
            setPlaying(!playing);
          }}
          aria-label={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? "Ⅱ" : "▶"}
        </button>
        <div className="time-readout">
          <strong>{current ? formatTime(current.at_minute) : "21:30"}</strong>
          <span>{step} / {events.length} events</span>
        </div>
        <label className="timeline-track">
          <span className="sr-only">Replay position</span>
          <input
            type="range"
            min={0}
            max={Math.max(events.length, 1)}
            value={step}
            onChange={(event) => {
              setPlaying(false);
              setStep(Number(event.target.value));
            }}
            style={{ "--timeline-progress": `${percentage}%` } as React.CSSProperties}
          />
        </label>
        <button
          className="reset-button"
          type="button"
          onClick={() => {
            setPlaying(false);
            setStep(0);
          }}
        >
          Reset
        </button>
      </div>
      <div className="event-readout" aria-live="polite">
        <span className={`event-dot event-${current?.type ?? "initial"}`} />
        <div>
          <strong>{current?.message ?? "Store state loaded. Start the governed replay."}</strong>
          <small>
            {current
              ? current.type.replaceAll("_", " ")
              : "Initial conditions · four consumers · five monitored loads"}
          </small>
        </div>
      </div>
    </section>
  );
}
