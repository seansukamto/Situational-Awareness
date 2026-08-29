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

The current MVP does **not** use GraphRAG, long-term LLM memory, autonomous
language-model actions, thousands of agents, or chat-with-agent features. Those
would add cost and apparent realism before the retail behaviour model is
calibrated. The deterministic engine also keeps matched baseline/intervention
runs reproducible and makes every safety ruling testable.

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

The Game Master is policy authority, not an LLM. A future language model may
explain events or suggest candidate actions, but it must not bypass the typed
action schema or deterministic validators.

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
