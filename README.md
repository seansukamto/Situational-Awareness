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

## Verification

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm run build
```
