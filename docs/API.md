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

## Staff game roster

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/avatars` | List the approved local 3D character catalog |
| GET/POST | `/api/projects/{project_id}/staff` | List or create project-scoped staff profiles |
| PUT | `/api/projects/{project_id}/staff/{staff_id}` | Update role, avatar, shift, authorization, or active state |
| POST | `/api/projects/{project_id}/staff/{staff_id}/reset-pin` | Replace the hashed staff game join PIN |

Staff names are unique within a project after whitespace and case
normalization. Avatar IDs are restricted to bundled local models, zone and
equipment authorization must reference the project's store snapshot, and PINs
are stored only as salted scrypt hashes. Authentication fields are never
returned by the API.

## Staff sustainability game

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/projects/{project_id}/task-templates` | List or create safe, reusable sustainability challenges |
| GET/POST | `/api/projects/{project_id}/game-days` | List or create dated game sessions |
| GET | `/api/projects/{project_id}/game-days/{game_day_id}` | Read a manager-visible game day and QR join token |
| POST | `/api/projects/{project_id}/game-days/{game_day_id}/start` | Snapshot active task templates into the day ledger |
| POST | `/api/projects/{project_id}/game-days/{game_day_id}/close` | Close the live task market without rewriting history |
| GET | `/api/game/join/{join_token}` | Read the scoped active roster for a QR join page |
| POST | `/api/game/join/{join_token}` | Verify staff PIN and issue a hashed, day-scoped bearer session |
| GET | `/api/game/tasks` | List eligible tasks, the player's own claims, and one personalized Game Master pick |
| POST | `/api/game/tasks/{task_id}/claim` | Atomically reserve one available task for the player |
| POST | `/api/game/tasks/{task_id}/release` | Return the player's claimed task to the market |
| POST | `/api/game/tasks/{task_id}/complete` | Complete once and award deterministic individual points |
| GET | `/api/game/leaderboard` | Read the scoped individual leaderboard |
| GET | `/api/projects/{project_id}/game-days/{game_day_id}/leaderboard` | Read the manager leaderboard |
| GET | `/api/projects/{project_id}/game-days/{game_day_id}/events` | Read the authoritative, sequence-numbered day ledger |
| GET | `/api/projects/{project_id}/game-days/{game_day_id}/analysis` | Read the structured post-close metrics, AI narrative, and learned policy version |
| GET | `/api/projects/{project_id}/game-policies` | Audit immutable learned policies and identify the active next-day version |

Task templates cannot reference protected equipment. Templates may use the
`energy`, `water`, `waste`, `food`, `transport`, or
`buying` domain. Non-equipment habits may target a known zone or the whole
store while equipment tasks inherit the equipment's authoritative zone and
role allow-list. Claim updates
use a versioned SQLite transaction so two staff members cannot win the same
task. Session tokens are returned once and stored only as SHA-256 hashes. Score
entries are unique per task instance, preventing duplicate completion points.
Leaderboards include every staff profile that joined the day, including
participants who have not yet earned points.
Closing a day is idempotent: it stores one structured analysis and one learned
policy for that ledger. OpenAI or Ollama is used only when the project's
allow-listed backend provider is configured; invalid or unavailable output
falls back to deterministic analysis. AI narrative is advisory. The automatic
policy surface is limited to validated per-domain point multipliers in the
`0.90`–`1.10` range, and each new game day snapshots the policy version it will
use. Data-only prior-day context is recorded in the day-start event so replay
and audits can show exactly what informed the Game Master. Verified completion
history can rank one eligible task as a personalized recommendation; it never
removes other eligible tasks, changes role/zone/equipment authority, or forces
an assignment.

## Error contract

Validation failures return `422`, missing resources return `404`, expired
checklists return `410`, oversized uploads return `413`, and impact analysis
without a confirmed bill returns `409`. Error bodies use FastAPI's `detail`
field.
