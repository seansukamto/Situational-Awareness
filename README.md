# Situational Awareness

Situational Awareness is a retail sustainability digital twin. It combines a
rule-governed store simulation, human-behaviour agents, auditable impact
calculations, and a Three.js replay experience so operators can compare an
existing workflow with a proposed intervention before piloting it in a store.

The first scenario is **Green Close**. Closing-shift staff are assigned safe,
non-critical shutdown tasks while the Game Master protects refrigeration,
safety systems, customer service, and other operational constraints. Green
Close is a scenario inside Situational Awareness, not the product name.

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
  and net operating impact.
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
- Green Close is currently the first intervention. The scenario switch is
  intentionally separate from the Situational Awareness product identity.

## Local development

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

Create the Singapore demo project and bill with:

```bash
curl -X POST http://127.0.0.1:8000/api/demo/bootstrap
```

Open `http://127.0.0.1:8000/docs` for the project, bill upload/confirmation,
scenario settings, simulation, and impact-analysis endpoints.

## Verification

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm run build
```
