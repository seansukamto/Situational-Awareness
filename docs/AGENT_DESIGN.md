# Agent and Game Master design

## What is borrowed from MiroFish

[MiroFish](https://github.com/666ghj/MiroFish) describes a workflow that turns
uploaded seed material into personas and an environment, runs a multi-agent
simulation with temporal memory, generates a report, and then supports deeper
interaction with agents. It builds on
[CAMEL-AI OASIS](https://github.com/camel-ai/oasis), whose environment advances
an agent graph through explicit actions and time steps.

Situational Awareness adopts the useful system pattern, not their code or their
claim of general-purpose prediction:

| Reference concept | Situational Awareness implementation |
|---|---|
| Seed material | Confirmed utility fields, store layout, equipment, roles, and scenario assumptions |
| Persona generation | Typed staff and consumer archetypes with bounded behavioural traits |
| Shared environment | One authoritative store state and clock |
| God's-eye intervention | A Game Master that schedules nudges and enforces operational policy |
| Temporal memory | An append-only, sequence-numbered event ledger and per-run agent state |
| Report agent | A deterministic decision brief grounded in the saved analysis |
| Interactive world | A Three.js replay reconstructed from the ledger |

The current vertical slice does **not** use GraphRAG, unbounded long-term
memory, autonomous state mutation, thousands of agents, or chat-with-agent
features. It does support constrained language-model proposals at meaningful
decision points. The deterministic engine remains the default and fallback,
keeping matched baseline/intervention runs operational without credentials and
making every safety ruling testable.

MiroFish is published under AGPL-3.0. This repository uses its public workflow
as design research and contains an independent implementation; no MiroFish code
is copied here. Any future code-level integration needs a separate licence and
deployment review.

## Agent interaction model

Staff and consumers are independent agents sharing the same world:

- consumer movement and exits change occupancy;
- occupancy changes the Game Master's action permissions;
- staff traits, fatigue, workload, time pressure, role, and intervention
  strength determine whether an action is proposed;
- the Game Master accepts or rejects the proposal against protected-load,
  customer-facing, role-authority, and current-state rules;
- accepted state changes alter later energy use and the replayed store;
- all baseline/intervention comparisons use the same per-agent random draw for
  a seed, so the intervention changes behaviour probability rather than luck.

The Game Master is policy authority, not an LLM. OpenAI or Ollama may suggest a
candidate action through the strict public `AgentProposal` schema, but cannot
bypass deterministic validators or perform authoritative arithmetic.

## Live staff game learning loop

The live game does not replay synthetic consumers or ask a model to mutate the
store. Staff voluntarily snatch safe task instances from an atomic marketplace.
Every join, claim, release, completion, and point award enters an immutable day
ledger. After close, OpenAI or Ollama may produce a strict structured narrative;
unavailable or invalid output falls back to deterministic analysis.

The narrative is advisory. The only automatically applied learning fields are
bounded domain point multipliers and a per-staff ordering of domains derived
from verified completion history. The next game day snapshots the exact policy
version and exposes one explainable Game Master pick while keeping every other
eligible task available. Model output cannot change protected equipment,
role/zone/equipment authority, verification status, score arithmetic, or any
employment decision.

## Provider and memory boundary

- `DeterministicAgentProvider` returns the existing paired-seed proposal.
- `OpenAIAgentProvider` uses the official SDK's Responses API with a strict JSON
  schema and `store=False`.
- `OllamaAgentProvider` uses an Ollama-compatible `/api/chat` endpoint with the
  same JSON schema.
- `BudgetedAgentProvider` supplies per-run/per-agent call limits, timeout,
  concurrency, token/cost ceilings, within-run request caching, usage tracking,
  and labelled deterministic fallback.

Observations contain only the current simulated time, actor archetype and
state, bounded nearby entities, permitted actions/targets, active intervention,
Game Master constraints, up to four recent public memories, and one bounded
summary of older memories. The response requests a short public rationale—not
hidden chain-of-thought. Raw prompts and sensitive personal information are not
persisted.

Each immutable paired run stores mode/provider/model metadata, a secret-free
configuration fingerprint, prompt and Game Master versions, settings snapshot,
public proposals, accept/reject outcomes, failures/fallbacks, latency and usage,
plus the existing configuration, evidence, metrics, and complete replay logs.

## Where the defensible moat can grow

The generic agent loop is not a moat. The defensible assets are retail-specific
and accumulate through deployment:

1. A versioned ontology linking store equipment, operating rules, roles,
   customer states, tariffs, and sustainability interventions.
2. A calibration dataset joining sub-meter readings, checklist outcomes, staff
   effort, customer incidents, and intervention exposure across stores.
3. Paired-scenario evaluation and back-testing that records prediction error,
   not just attractive simulations.
4. Reusable policy packs for different retail formats and jurisdictions,
   validated with facilities and operations teams.
5. A trusted decision workflow: evidence labels, protected-load guarantees,
   audit trails, uncertainty ranges, and pilot recommendations.

## Recommended evolution

1. Import an actual floor plan and equipment inventory instead of the demo
   layout.
2. Add pilot-observation ingestion and fit trait distributions to measured task
   completion and dwell-time data.
3. Add explicit short-term observations to agents only after there is evidence
   for how team progress changes behaviour.
4. Add more scenarios through the existing typed extension points.
5. Use LLMs last, for constrained persona drafting and event explanation, with
   deterministic simulation and policy enforcement retained underneath.
