import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { completeChecklistTask, fetchChecklist } from "../api";

export function ChecklistPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const checklist = useQuery({
    queryKey: ["checklist", token],
    queryFn: () => fetchChecklist(token),
    retry: false,
  });
  const completion = useMutation({
    mutationFn: (taskId: string) => completeChecklistTask(token, taskId),
    onSuccess: (updated) => queryClient.setQueryData(["checklist", token], updated),
  });

  if (checklist.isLoading) {
    return <main className="checklist-shell checklist-loading">Loading today’s checklist…</main>;
  }
  if (checklist.error || !checklist.data) {
    return (
      <main className="checklist-shell checklist-error">
        <span className="brand-mark">SA</span>
        <h1>This checklist is unavailable</h1>
        <p>{checklist.error instanceof Error ? checklist.error.message : "Ask your shift manager for a new QR code."}</p>
      </main>
    );
  }

  const completed = checklist.data.tasks.filter((task) => task.completed_at).length;
  const progress = completed / Math.max(checklist.data.tasks.length, 1) * 100;
  return (
    <main className="checklist-shell">
      <header className="checklist-header">
        <div className="side-brand"><span className="brand-mark">SA</span><div><strong>Situational</strong><span>Awareness</span></div></div>
        <span className="checklist-access">Checklist access</span>
      </header>
      <section className="checklist-intro">
        <span className="kicker">{checklist.data.scenario_label}</span>
        <h1>Close safely, one zone at a time.</h1>
        <p>{checklist.data.store_name}</p>
        <div className="mobile-progress"><span style={{ width: `${progress}%` }} /></div>
        <small>{completed} of {checklist.data.tasks.length} tasks confirmed</small>
      </section>
      <section className="task-list" aria-label="Closing tasks">
        {checklist.data.tasks.map((task, index) => {
          const done = Boolean(task.completed_at);
          return (
            <button
              key={task.id}
              type="button"
              className={done ? "task-row completed" : "task-row"}
              disabled={done || completion.isPending}
              onClick={() => completion.mutate(task.id)}
            >
              <span className="task-check">{done ? "✓" : String(index + 1).padStart(2, "0")}</span>
              <span className="task-copy"><strong>{task.label}</strong><small>{task.zone_label} · {task.assigned_role}</small></span>
              <span className="task-action">{done ? "Done" : "Confirm"}</span>
            </button>
          );
        })}
      </section>
      <aside className="safety-note">
        <strong>Protected systems stay on</strong>
        <p>{checklist.data.safety_note}</p>
      </aside>
      {checklist.data.status === "completed" && (
        <section className="checklist-complete"><span>✓</span><div><strong>Green Close complete</strong><p>Your shift manager can now see the completion state.</p></div></section>
      )}
      <footer className="checklist-footer">Link expires {new Date(checklist.data.expires_at).toLocaleString()}</footer>
    </main>
  );
}
