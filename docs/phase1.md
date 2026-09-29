# Phase 1: execution workbench

For the unified SPEED login, model configuration/health and current Linux
validation sequence, see [the runtime runbook](phase1-runtime.md).
The integrated chat supports local demo login with SPEED_DEMO_AUTH=true; the
default false preserves JWT authentication. Demo mode does not auto-approve tools.

## Architecture

Existing `TaskService` remains the task/ownership source. `AgentService` adds an
in-memory execution record and bounded background jobs, without replacing the
legacy `/api/v1/tasks` API. The agent namespace starts orchestration; legacy tasks
only create records. `SecurityGateway`, JWT authentication, RBAC, consent,
`ToolRegistry`, `ToolRuntime`, `ModelRouter`, and `InferenceService` are reused.

- `Planner`: requests structured JSON from the configured reasoning model through
  existing inference. A 30-second default timeout, model absence, malformed JSON,
  invalid graph or unregistered tool triggers a disclosed deterministic fallback.
  Document fallback plans still run real analysis and tools; coding planning errors
  fail rather than substituting an example program. Analysis errors fail the step.
  `demo_mode=true` is rejected by the public API. Phase 1 inference accepts loopback
  endpoints only. Prompts and model responses are never included in trace events.
- `ExecutionPlan` / `PlanStep`: Pydantic source of truth, at most 32 steps. Rejects
  duplicate IDs, missing/self/duplicate dependencies, cycles, unknown execution
  kinds, non-pending initial states, unknown tools and invalid input references.
  Inputs may reference a **direct dependency** with `{"from_step":"step-id"}`.
- `TaskGraph`: readiness, transitive failure blocking and topological ordering.
  No graph library or framework is needed for this bounded DAG.
- `Executor`: pending → ready → running → completed/failed; consent adds waiting.
  Starts independent nodes, waits for the first completion and immediately unlocks
  dependents. Fan-in requires every dependency to complete. Failed descendants are
  blocked, while unrelated branches can finish. A shared semaphore bounds runtime
  concurrency (default 3) across all agent tasks. Shutdown cancels retained jobs.
- `RuntimeRouter`: distinct native, inference, sandbox, MCP and artifact adapters.
  Privileged steps go through `SecurityGateway`; MCP and sandbox retain mandatory
  task/resource-specific consent. The dashboard presents approve/deny actions using
  existing `/api/v1/permissions/{consent_id}/approve` and `/deny` endpoints. Requests
  expire after ten minutes; denial or expiry fails the step and blocks dependents.
- `ExecutionEvent` / `EventBus`: action-level events, per-task monotonically
  increasing sequence, task/step/lane IDs, parent event, timestamps, durations,
  status and mock provenance. No per-token stream. Metadata has an allow-list;
  exception strings, document contents, raw stdout, prompts and JWTs are excluded.
  Structured logs include identifiers and state only.

## Dashboard and WebSocket contract

`/phase1/` is static HTML/CSS/JavaScript/SVG served by FastAPI; no frontend build,
CDN, external fonts, visualization library or fake frontend workflow animation.
The dark history view has stable colored lanes, action dots, dependency curves,
fan-out and fan-in, current-action highlighting, state pills, safe
expandable metadata, category highlighting, follow/pause scrolling and downloads.
Category highlighting dims other rows to preserve graph geometry.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/agent/tasks` | Start asynchronously; returns 202 and task ID |
| `GET /api/v1/agent/tasks/{id}` | Ownership-protected snapshot |
| `GET /api/v1/agent/tasks/{id}/events?after_sequence=0` | Ordered retained events plus snapshot |
| `POST /api/v1/agent/tasks/{id}/ticket` | JWT-authenticated, 30-second single-use WS ticket |
| `WS /api/v1/agent/tasks/{id}/events` | First-frame authentication and live replay |
| `GET /api/v1/agent/tasks/{id}/artifacts/{artifact_id}` | Registered artifact download only |
| `POST /api/v1/agent/tasks/{id}/review` | Owner records a result decision and optional comment |

REST uses `Authorization: Bearer <JWT>`. The standalone debug UI signs in through the existing
`POST /api/v1/auth/login` endpoint. Tokens remain in browser memory, not storage or
URLs. After refresh, sign in again; the URL fragment retains only the task ID.

WebSocket first message, within ten seconds:

```json
{"ticket":"<single-use-ticket>","after_sequence":12}
```

The server atomically subscribes and captures replay, then sends:

```json
{"type":"snapshot","snapshot":{"task_id":"...","last_sequence":15},"events":[],"history_truncated":false}
```

The actual snapshot also contains objective, status, planner mode, safe step
summaries/dependencies, running steps, artifacts and final summary. Private step
inputs/results are omitted. Replay contains all retained events after the requested
sequence. Subsequent frames are `{"type":"event","event":{...}}`; idle connections
receive heartbeat frames every 20 seconds. Clients deduplicate by sequence.

One event shape:

```json
{"event_id":"...","sequence":16,"task_id":"...","step_id":"read-report",
 "parent_event_id":"...","agent_id":"speed","lane_id":1,"event_type":"file.read",
 "status":"completed","title":"file.read fixtures/inspection-report.txt","summary":"",
 "timestamp":"...","duration_ms":null,"metadata":{"path":"fixtures/inspection-report.txt","size":384},"is_mock":false}
```

Lane numbers are assigned once in topological order, one per step. All sub-actions
stay in that lane. `step.started` includes direct dependency IDs and source lanes;
the renderer connects their actual completion rows. Root events use lane zero.
No Git commands are invoked by the runtime.

History retains 2,000 events per task. Truncation is explicit. Subscriber queues
hold 256 events; slow consumers receive a reconnect close (1013) and replay.
Unknown/foreign tasks are 404 over REST; invalid WS authentication closes 4401;
invalid cursors close 4400. Tickets are bound to owner and task. No task data is
sent before authentication. Single process only; do not use multiple workers.

NGINX forwards `/api/v1/` to FastAPI with Upgrade/Connection headers and forwards
`/phase1/` to the dashboard. Existing `/v1/` routing and special llama.cpp stream
routes remain intact. The root llama.cpp UI remains at `/`.

## Tools, sandbox, MCP and documents

Native tools: `file.list`, `file.read`, `file.write`. Relative paths resolve against
`SPEED_WORKSPACE` (default repository root), not the current working directory.
Absolute paths, `..`, and resolved symlink escapes are rejected. Reads/writes are
limited to 1 MB. Write events report created/updated and added/removed line counts.
`ToolRuntime` emits the trace for actual operations within an execution context.
Filesystem resolution does not defend against a concurrent hostile host process
swapping symlinks between checks; this is a trusted local workspace demo.

`SPEED_SANDBOX_MODE` is `disabled` by default:

- Simulation is available only through test constructor injection, never deployment
  configuration or task requests. Existing `SPEED_SANDBOX_MODE=mock` configurations
  must be changed to `disabled` or `docker` before restarting.
- `docker`: Docker CLI adapter, ephemeral container, `--pull=never`, no network,
  non-root UID, read-only root, dropped capabilities, no-new-privileges, temporary
  tmpfs workdir, CPU/memory/PID limits, bounded timeout (max 30 seconds), bounded
  stdout/stderr capture, exit code and forced cleanup. Code travels over stdin;
  no host workspace or Docker socket is mounted into the container. Missing Docker
  or image fails the step truthfully; it does not silently become a mock.

Docker sandboxing is not hardened hostile multi-tenant isolation. The image is
operator-configured (`SPEED_SANDBOX_IMAGE`, default `python:3.13-slim`) and must be
preloaded; no image pull happens automatically.

MCP uses the official v2 SDK, `Client(StdioServerParameters(...))` and `MCPServer`.
Only the bundled `demo_mcp.py` definition can start, using the active Python
interpreter. There is no user-supplied executable, server URL or Internet transport.
Client context exit closes the process; the whole call has a 20-second timeout.
Tools are discovered and checked, error results fail the step. `calculator` supports
add/multiply without eval. `search_internal_docs` searches two bundled fixture
policies by keyword. This is an actual local protocol path, not RAG. Authentication
demo mode does not change model or tool execution.
SDK reference: https://py.sdk.modelcontextprotocol.io/client/transports/

`ArtifactRuntime` uses python-docx to write actual OOXML documents, supporting title,
paragraphs, headings, bullets and rectangular tables. Artifacts live under
`outputs/tasks/{task_id}/{artifact_id}/approval-note.docx`. Downloads use registered
IDs plus ownership and path containment checks, never a caller-supplied host path.
Mock-derived content gets a visible document notice; the DOCX container itself is
real. Content defaults to human-review language, not an automatic approval claim.
API reference: https://python-docx.readthedocs.io/en/latest/user/quickstart.html

## Normal chat and developer inspection

The Phase 1 experience is now integrated into the existing llama/SPEED chat.
See [Phase 1 chat integration](phase1-chat.md) for connection, persistence,
source architecture and server-only build/test instructions. `/phase1/` below
remains the developer inspection and fallback demo page.

## Launch on an authorized execution machine only

**These instructions were not run during the edit-only Mac session.** No local
execution, package installation, lock generation or Docker/MCP startup was performed.

1. On a machine authorized to execute SPEED, resolve/install the declared
   dependencies from the repository root. `uv.lock` is intentionally unchanged in
   this edit-only patch; do not claim `--locked` works until it is regenerated.

   ```sh
   uv lock
   uv sync
   ```

   For an offline deployment, prepare the dependency/image cache on an approved
   connected machine and transfer it by your normal process. MCP and DOCX require
   `mcp>=2,<3` and `python-docx>=1.2,<2`. WebSocket serving uses `websockets`.

2. Set `SPEED_JWT_SECRET` to a private deployment value via your normal secret
   configuration. Set `SPEED_WORKSPACE` to the checkout (or another directory with
   the sample report copied under `fixtures/`). No default signing secret was added.
   Existing demo users are still in `backend/app/security/store.py`; use an existing
   administrator/developer account. The regular `user` role cannot start agents.
   Existing sample accounts are not a production authentication system.

3. From the repository root, on that authorized machine:

   ```sh
   PYTHONPATH=backend uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```

4. Open `http://127.0.0.1:8000/phase1/` (or the existing gateway at
   `http://127.0.0.1:9100/phase1/` after loading the reviewed NGINX configuration).
   Sign in. Choose **Document review** and start
   “Read the sample inspection report and prepare an approval note.”
   Watch read → parallel analysis/risk → draft → save → DOCX; download the document.
   The configured local reasoning model must be available for analysis.

5. Choose **Document + local MCP** to add real fixture search. Approve the specific
   MCP consent when shown. Denial produces a failed branch and blocked dependents.

6. For sandbox execution, configure `SPEED_SANDBOX_MODE=docker` with a preloaded
   image. Choose the coding workflow and approve the specific tool permission.
   Invalid/unavailable planner output fails; no example program is substituted.

7. Configure the available local reasoning endpoint in `config/models/models.yaml`.
   Existing model paths must match the deployment. Document planning fallback is
   labelled explicitly; model analysis never silently becomes a source extract.

Equivalent task request, after obtaining a JWT through the existing login API:

```http
POST /api/v1/agent/tasks
Authorization: Bearer <JWT>
Content-Type: application/json

{"objective":"Prepare an inspection approval note","flow":"document","input_path":"fixtures/inspection-report.txt"}
```

## Tests to run elsewhere

```sh
uv run pytest tests/phase1
SPEED_TEST_DOCKER=1 uv run pytest tests/phase1/test_adapters.py -m docker
```

The mandatory Phase 1 suite uses no GPU/cloud/Internet/Docker. Its MCP integration
starts a local stdio child; DOCX tests generate/reopen temporary documents. Docker
has mocked unit coverage and an explicitly enabled integration test. The pre-existing
GPU benchmark remains at `tests/task_routing/test_laya.py`, runnable explicitly on
suitable hardware; default test discovery targets the Phase 1 suite.

## Limits

In-memory state is lost on restart; artifacts remain on disk but are no longer
registered for download. Restart is required after 100 retained tasks; at most eight
agent jobs are accepted concurrently. No distributed scheduling, cancellation API,
retry engine, durable audit trail or task list exists. Browser reload requires login.
DAGs may be wider than the viewport and scroll horizontally. UI behavior, gateway
configuration and all execution paths still require validation on an authorized
machine. No OCR, vector retrieval, PPTX, XLSX, cloud model service or production
sandbox hardening is claimed.
