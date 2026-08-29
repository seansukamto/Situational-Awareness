# API reference

Interactive OpenAPI documentation is available at `/docs` while the FastAPI
service is running.

## Simulation

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service health |
| GET | `/api/demo/store` | Initial synthetic store model |
| GET | `/api/scenarios` | Available scenario configurations |
| POST | `/api/simulations/run` | Deterministic single run |
| GET | `/api/simulations/compare` | Matched baseline/intervention comparison |
| GET | `/api/simulations/explanations` | Event-sequence-grounded explanations |

## Agent intelligence

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/ai/status` | List deterministic/OpenAI/Ollama availability and model names without credentials |
| POST | `/api/ai/test` | Request one minimal structured proposal from the selected configured provider |

`POST /api/ai/test` returns a safe non-success response when an optional
provider is missing or unavailable. It never returns provider credentials or a
raw exception containing secret configuration.

## Projects, bills, and impact

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/demo/bootstrap` | Idempotently create or upgrade demo data |
| GET/POST | `/api/projects` | List or create projects |
| GET | `/api/projects/{project_id}` | Read a project |
| PUT | `/api/projects/{project_id}/settings` | Update uncertainty inputs |
| PUT | `/api/projects/{project_id}/agent-settings` | Save default mode and provider budgets |
| GET | `/api/projects/{project_id}/bills` | List extracted bills |
| POST | `/api/projects/{project_id}/bills/upload` | Parse a bill without retaining the raw file |
| POST | `/api/projects/{project_id}/bills/{bill_id}/confirm` | Confirm or correct extracted fields |
| POST | `/api/projects/{project_id}/analysis` | Run a Monte Carlo impact analysis |
| GET | `/api/projects/{project_id}/analyses/{analysis_id}/report.md` | Download a grounded decision brief |
| POST | `/api/projects/{project_id}/runs` | Create one persisted paired baseline/intervention run |
| GET | `/api/projects/{project_id}/runs` | List project-isolated run history newest first |
| GET | `/api/projects/{project_id}/runs/{run_id}` | Read immutable snapshots, results, agent audit, and replay logs |

Run creation accepts `seed`, `sample_count`, `mode`, `model`, maximum calls,
calls per agent, timeout, concurrency, token budget, and estimated USD cost cap.
The requested model must match the backend-approved configured model. A single
record always contains both baseline and intervention results.

## Staff handoff and privacy

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/projects/{project_id}/checklists` | Create a 24-hour scoped checklist token |
| GET | `/api/checklists/{token}` | Read the authorized mobile checklist |
| POST | `/api/checklists/{token}/tasks/{task_id}/complete` | Confirm one authorized task |
| GET | `/api/privacy` | Machine-readable storage and retention summary |

## Error contract

Validation failures return `422`, missing resources return `404`, expired
checklists return `410`, oversized uploads return `413`, and impact analysis
without a confirmed bill returns `409`. Error bodies use FastAPI's `detail`
field.
