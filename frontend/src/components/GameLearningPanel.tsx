import type { GameDayAnalysis, LearnedGamePolicy, SustainabilityDomain } from "../types";


const DOMAINS: SustainabilityDomain[] = ["energy", "water", "waste", "food", "transport", "buying"];


function percentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}


export function GameLearningPanel({
  analysis,
  policy,
  loading,
}: {
  analysis?: GameDayAnalysis;
  policy?: LearnedGamePolicy;
  loading: boolean;
}) {
  if (loading) {
    return <section className="game-learning-panel game-learning-loading">Analyzing the recorded staff game day…</section>;
  }
  if (!analysis) {
    return <section className="game-learning-panel game-learning-loading">The structured end-of-day analysis will appear after the game closes.</section>;
  }
  const metrics = analysis.metrics;
  return (
    <section className="game-learning-panel" aria-label="End-of-day game analysis">
      <div className="game-learning-heading">
        <div>
          <span>05 · Learning loop</span>
          <h2>End-of-day Game Master analysis</h2>
          <p>{analysis.narrative.summary}</p>
        </div>
        <div>
          <small>{analysis.fallback_used ? "Safe deterministic fallback" : `${analysis.provider} analysis`}</small>
          <strong>{analysis.learned_policy_version}</strong>
          <span>{analysis.prompt_template_version}</span>
        </div>
      </div>

      <div className="game-learning-metrics">
        <div><span>Participation</span><strong>{metrics.participating_staff}/{metrics.active_staff_profiles}</strong><small>joined profiles</small></div>
        <div><span>Completion</span><strong>{percentage(metrics.completion_rate)}</strong><small>{metrics.tasks_completed}/{metrics.tasks_released} tasks</small></div>
        <div><span>Individual points</span><strong>{metrics.total_points}</strong><small>engagement only</small></div>
        <div><span>Released back</span><strong>{metrics.tasks_released_back}</strong><small>task-friction signal</small></div>
      </div>

      <div className="game-learning-body">
        <article>
          <span>Observed patterns</span>
          <ul>{analysis.narrative.patterns.map((pattern) => <li key={pattern}>{pattern}</li>)}</ul>
        </article>
        <article>
          <span>Next-day recommendations</span>
          <ul>{analysis.narrative.recommendations.map((recommendation) => <li key={recommendation}>{recommendation}</li>)}</ul>
        </article>
        <article className="game-policy-audit">
          <span>Bounded policy update</span>
          <p>Only validated domain point weights can change automatically. Safety, task authority, protected loads, and employment decisions remain outside the learning loop.</p>
          <div>
            {DOMAINS.map((domain) => {
              const multiplier = policy?.domain_point_multipliers[domain] ?? 1;
              const performance = metrics.domain_performance[domain];
              return (
                <div key={domain}>
                  <b>{domain}</b>
                  <span>{performance ? `${performance.completed}/${performance.released} complete` : "No tasks"}</span>
                  <strong className={multiplier !== 1 ? "adjusted" : ""}>{multiplier.toFixed(2)}×</strong>
                </div>
              );
            })}
          </div>
        </article>
      </div>
      {policy && (
        <details className="game-policy-details">
          <summary>Inspect learned prompt context and guardrails</summary>
          <div><span>Data-only prompt context</span><ul>{policy.prompt_context.map((item) => <li key={item}>{item}</li>)}</ul></div>
          <div><span>Permanent guardrails</span><ul>{policy.guardrails.map((item) => <li key={item}>{item}</li>)}</ul></div>
        </details>
      )}
    </section>
  );
}
