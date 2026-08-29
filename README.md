# Situational Awareness

[![CI](https://github.com/seansukamto/Situational-Awareness/actions/workflows/ci.yml/badge.svg)](https://github.com/seansukamto/Situational-Awareness/actions/workflows/ci.yml)

Situational Awareness is a retail sustainability digital twin. It combines a
rule-governed store simulation, human-behaviour agents, auditable impact
calculations, and a Three.js replay experience so operators can compare an
existing workflow with a proposed intervention before piloting it in a store.

The first scenario is **Green Close**. Closing-shift staff are assigned safe,
non-critical shutdown tasks while the Game Master protects refrigeration,
safety systems, customer service, and other operational constraints. Green
Close is a scenario inside Situational Awareness, not the product name.

Requires Python 3.11+ and Node.js 22 (recommended). No Docker service is needed.

## Architecture

- `backend/`: FastAPI API and authoritative simulation engine.
- `frontend/`: React, TypeScript, and React Three Fiber application.
- `data/`: versioned demo inputs and reference datasets.

## Data and evidence model

- Uploaded PDF, JSON, CSV, or TXT bills are parsed in memory; the raw file is
  discarded and extracted fields require manager confirmation.
- SQLite stores project configuration, confirmed bill fields, and analysis
  outputs locally. Set `SA_DATABASE_PATH` to choose the database location.
- Impact analysis runs matched-seed Monte Carlo comparisons and returns P10,
  P50, and P90 ranges for energy, cost, emissions, staff time, task completion,
  customer-service incidents, net operating impact, and profit-margin impact.
- Every output labels measured, derived, assumed, and simulated evidence. The
  synthetic bill in `data/demo/` is fictional and safe for demonstrations.

## Simulation replay

- The Python Game Master advances a deterministic store clock and evaluates
  staff proposals against role, equipment-criticality, and customer-presence
  constraints.
- Staff and individual consumer agents move through the same authoritative
  world. Baseline and intervention runs use paired random draws so the
  intervention changes probabilities rather than the underlying random event.
- React Three Fiber reconstructs the world from the append-only event ledger.
  Replay controls never mutate the simulation; they project state at a chosen
  event sequence number.
- Animated character models are loaded locally from `frontend/public/models`.
  See the bundled [model attribution](frontend/public/models/ATTRIBUTION.md).
- Green Close is currently the first intervention. The scenario switch is
  intentionally separate from the Situational Awareness product identity.

## Hybrid agent intelligence

Every staff and consumer decision uses the same provider contract. The default
`DeterministicAgentProvider` needs no credentials; optional
`OpenAIAgentProvider` and `OllamaAgentProvider` implementations may propose a
strictly typed public action and rationale. The Game Master still validates and
applies every state change, and all energy, cost, emissions, labour, and profit
calculations remain deterministic code.

Configure an optional provider only on the backend:

```bash
# Cloud mode (official OpenAI SDK and Responses API)
export OPENAI_API_KEY="..."
export OPENAI_MODEL="your-approved-model"

# Or local Ollama-compatible mode
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export OLLAMA_MODEL="your-local-model"
```

No key is accepted by or returned to the browser. Missing credentials, network
timeouts, invalid structured output, and exhausted call/token/cost budgets emit
auditable failure/fallback events and continue with deterministic behaviour.
OpenAI cost is an estimate only and remains zero unless the optional per-token
rates in `.env.example` are configured.

## Manager and staff workflow

- Managers can upload a bill, review every extracted field, change scenario
  assumptions, compare matched baseline/intervention runs, and download a
  Markdown decision brief grounded in the saved analysis.
- The **Staff handoff** action creates a random, 24-hour checklist token and a
  scannable QR code. The mobile view exposes closing tasks only—never utility,
  cost, or assumption data.
- The live staff-game API supports project-scoped profiles, local 3D avatars,
  dated QR sessions, an atomically claimed task marketplace, deterministic
  individual points, and a sequence-numbered leaderboard ledger. Managers can
  configure the roster, launch the QR session, watch the leaderboard, and
  replay the recorded staff interactions across the operating day with no
  simulated consumers mixed into the evidence.
- Closing a game day produces a structured AI analysis with deterministic
  fallback and an immutable learned-policy version. Only server-validated
  domain point multipliers between `0.90x` and `1.10x` may carry into the next
  day; protected loads, staff authority, and employment decisions remain
  permanent guardrails outside the learning loop. Prior verified completions
  also personalize one visible **Game Master pick** per player while leaving
  every eligible task available to snatch.
- Protected equipment is excluded from the staff checklist. The public task
  API accepts only task IDs already authorized in that checklist session.
- Event explanations cite the exact event sequence, time, transition, and
  operating rules. Behavioural events use medium confidence; deterministic
  safety rulings use high confidence.
- Raw utility files are parsed in memory and discarded. Uploaded filenames are
  normalized before storage to avoid retaining accidental personal metadata.

## Local development

For a one-command dependency setup:

```bash
make setup
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The web application expects the API at `http://127.0.0.1:8000`. Set
`VITE_API_URL` to override it.

Docker is intentionally not required for the MVP. Local Python, Node.js, and
SQLite keep the hackathon setup fast; containerization can be added later when
deployment targets justify it.

Create the Singapore demo project and bill with:

```bash
curl -X POST http://127.0.0.1:8000/api/demo/bootstrap
```

Open `http://127.0.0.1:8000/docs` for the project, bill upload/confirmation,
scenario settings, provider status/test, persisted simulation, and
impact-analysis endpoints.

See the [architecture guide](docs/ARCHITECTURE.md),
[agent-design reference](docs/AGENT_DESIGN.md), and [API reference](docs/API.md)
for implementation and extension details.

## Verification

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm test && npm run build
```
