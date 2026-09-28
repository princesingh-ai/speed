# Phase 1 in the existing chat

This integration uses the vendored Svelte UI under `llama.cpp/tools/ui` on
`feature/phase1-agent-orchestration`. It adds no UI dependencies and creates no
second conversation system. `/phase1/` remains a developer inspection/demo view.

## Use

Ordinary chat remains the default, including small questions, manual model
selection, existing tool calls, MCP attachments and the llama agentic loop.
Enable **SPEED agent** above the composer to submit a Phase 1 workflow. Open
**Connect to SPEED**, authenticate with a SPEED account authorized for agent
execution, and select Document, Document + local MCP, or Coding sandbox.
SPEED and Snap have separate authentication domains. SPEED credentials/tokens
are memory-only; refresh requires connecting again. Snap logout also disconnects
SPEED. The local-agent label describes execution on the server workspace, not an
air-gap or a guarantee about all ordinary-chat tools.

Enter the report's server-workspace-relative path. Browser uploads and chat
history are not part of `StartRequest`; attachments are rejected before clearing
the composer. SPEED requests contain the new objective and selected workflow
options only. The standard manual model selector remains available for ordinary
chat; SPEED uses backend automatic routing. Demonstration analysis is explicitly
labelled, and can still invoke real native tools, MCP, or the configured sandbox.

The existing `chatStore.sendMessage` dispatches the selected mode. A SPEED turn
uses the existing IndexedDB conversation and message tree to persist its user
message and assistant anchor before POSTing `/api/v1/agent/tasks`. The returned
task ID is attached to that anchor. Existing queued ordinary-chat messages retain
their original mode even if the user later changes the composer toggle.

The visible order is user prompt, live execution activity, the actual backend
final response through the existing assistant Markdown renderer, then artifact
cards. Running tasks open the activity automatically; completed tasks collapse;
failed tasks remain open. An explicit user toggle takes precedence. There is no
pretend cancel action: navigating away only closes the observer, not the task.

## Activity and graph

Events are ordered by sequence, deduplicated, isolated by task ID, and bounded to
2,000 retained events per mounted trace. The current backend executes one runtime
operation per plan step, so one step ID maps to one row. `step.ready`,
`step.started`, `step.waiting`, `step.resumed`, `step.completed` and `step.failed`
update the same row; file/tool/model/sandbox/MCP/artifact metadata enrich it.
Planning is a single separate row. Snapshot statuses supersede older replayed
events; truncated history is explicitly indicated.

Examples include `Read fixtures/inspection-report.txt`, an edit with `+18 / -3`,
`Sandbox: python calculation` with an exit code, `MCP: search_internal_docs` with
a result count, and `Create approval-note.docx`. Only emitted metadata is shown.
Relative paths are validated before display. File contents, arbitrary metadata,
prompts, command source, stdout/stderr and credentials are not rendered in activity.
The separately requested final response may contain reviewed source material.

The compact SVG lanes derive from the plan's dependencies in deterministic
topological order. A linear chain continues in one lane; independent roots or
fan-out allocate separate lanes; each dependency has its own edge into a fan-in.
There are no commit objects or decorative graph edges. Rows follow first observed
sequence order; missing rows are restored from the plan. Lane IDs from backend
debug telemetry are deliberately compacted because the backend assigns one ID
per step, including linear steps. Wide plans scroll horizontally. This is an
execution graph, not Git history. Shared Button primitives and existing theme
tokens are used; existing llama tool/MCP/sandbox renderers remain intact.

The dependency-aware graph normalizer lives in `src/lib/speed/trace.ts`. The
standalone debug page remains unchanged; sharing TS/Svelte code with its plain
JavaScript bundle would require an additional build integration and is deferred.

## Transport, security and persistence

All HTTP routes use same-origin `/api/v1`. A mounted task observer requests a
single-use task-bound ticket and derives `ws:`/`wss:` from the page origin. The
ticket and replay cursor are sent in the first WebSocket frame. JWTs never appear
in URLs. No healthy-stream polling is used. Snapshots are refreshed on lifecycle
events; reconnect uses a fresh ticket, bounded exponential backoff, heartbeat
timeout detection and the last accepted sequence. A sequence gap forces replay.
Unmount closes the socket and cancels retries/HTTP work. Reopening requests a full
bounded replay plus current snapshot. HTTP 401/403/404 stop automatic retries and
show an actionable message. A reconnect button never starts another agent task.

`DatabaseMessage.speedTask` stores conversation ID, parent user-message ID,
owner ID, task ID, and the latest snapshot. This optional, unindexed field needs
no Dexie schema/index migration. Persisted final content uses the existing
message content field. Updates never append to another active conversation or
recreate a deleted message. A copied/forked link with changed conversation or
parent IDs cannot subscribe or download; its existing prose remains readable.
Task connections are not shared across owners. Snapshots and final messages are
stored in the browser, just like existing chat history; tokens are not.

Approve/Reject uses the existing authenticated permission endpoints and requires
an explicit click. Backend RBAC, ownership, expiry and task-bound WebSocket
ticket checks remain authoritative. Artifact cards use registered task/artifact
IDs to construct an authenticated download request, ignoring server/imported URL
fields. The backend retains ownership and path-containment checks. No host path
is displayed and no unauthenticated download link is generated.

The backend addition is `AgentRecord.final_response` in the protected task
snapshot. On successful execution it retains the actual last textual LLM or
verification result in topological order; a tool-only plan returns the backend's
completion status. Failed workflows expose the existing failure summary, not a
fabricated success statement. Final response content is never put in EventBus
metadata. The response is not a new summarizing model call.

## Tests written, not executed locally

The existing Vite test projects discover:

- `tests/unit/speed-trace.test.ts`: sequence/replay isolation, coalescing, paths,
  redaction, edit counts, linear/parallel/fan-in geometry, mock/consent/MCP/sandbox.
- `tests/unit/speed-api.test.ts`: first-frame auth, replay cursor, duplicate/gap
  handling, healthy-stream behavior, unmount, terminal replay, HTTP auth errors,
  single-attempt task creation, secure artifact route and explicit consent POST.
- `tests/unit/speed-messages.test.ts`: persisted task-turn association and safe
  updates while another conversation is active.
- `tests/client/speed-activity.svelte.test.ts`: mounted inline activity, lifecycle
  disclosure behavior, manual choice, mock/consent, artifact order, owner isolation.
- `tests/unit/speed-fixtures.ts` and `tests/client/SpeedActivityHarness.svelte`
  support these tests.

Backend `tests/phase1/test_execution.py` checks real final-result retention and
empty results on failure. `test_api.py` checks owner-only result access and absence
of result text in events. All tests require execution on an authorized machine.
No passing test/build/typecheck claim is made for the Mac edit-only session.

## Commands for the authorized server operator

Run from the SPEED server checkout, after reviewing its local changes. No
submodule initialization is needed: llama.cpp is normal tracked source despite
the leftover `.gitmodules` entry in the imported revision.

```sh
git switch feature/phase1-agent-orchestration
git pull --ff-only origin feature/phase1-agent-orchestration
```

This UI patch changes no manifests or lockfiles. The earlier Phase 1 Python
manifest already added dependencies without updating `uv.lock`; resolve that
separately on the authorized machine and review the resulting lockfile:

```sh
uv lock
uv sync
uv run pytest tests/phase1
npm --prefix llama.cpp/tools/ui ci
npm --prefix llama.cpp/tools/ui run check
npm --prefix llama.cpp/tools/ui run test:unit -- --run tests/unit/speed-trace.test.ts tests/unit/speed-api.test.ts tests/unit/speed-messages.test.ts
npm --prefix llama.cpp/tools/ui run test:client -- --run tests/client/speed-activity.svelte.test.ts
npm --prefix llama.cpp/tools/ui run build
```

Client tests require the deployment's existing Playwright Chromium installation.
Prepare approved package/browser caches separately if the machine is offline.
The earlier Python MCP version requirement must also be resolved against the
operator's approved package index; this session did not install or verify it.

The inspected CMake integration embeds `tools/ui/dist` into llama-server. Building
only the UI does not update an already-running binary. Assuming the deployment's
existing build directory is `llama.cpp/build`, preserve its cached GPU/toolchain
options and use the freshly built source assets rather than downloaded prebuilt UI:

```sh
cmake -S llama.cpp -B llama.cpp/build -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build llama.cpp/build --target llama-server --parallel
```

If the deployment uses a different build directory, substitute that existing
directory in both commands. Restart the deployment's llama-server process using
its existing model/router arguments and supervisor; restart the SPEED backend to
load `final_response`. No service-unit names or launch flags are recorded in this
checkout, so an exact `systemctl restart` command cannot truthfully be supplied.
The existing gateway `/api/v1/` WebSocket proxy already supports this integration;
no NGINX change or reload is required by this patch. For UI development only,
point `VITE_PUBLIC_SERVER_ORIGIN` at the gateway; Vite now proxies `/api/v1` and WS
to that same configured origin. Do not point it at llama-server alone.

After restart, reopen the gateway chat (and accept the PWA update if offered),
connect SPEED, and try the document workflow with demonstration analysis. Verify
file read, parallel analysis, merge, final prose and DOCX download; reopen the
conversation and reconnect. Then verify explicit MCP/sandbox approval and denial
on the authorized machine. Do not claim this checklist was exercised on the Mac.

## Phase 1 limits

- Server task registry/history is in-memory; restart loses replay and registered
  downloads. Previously persisted browser prose/snapshots remain visible with an
  unavailable-task notice. Full event history is not persisted in IndexedDB.
- Refresh before the task POST returns can orphan the task-to-message link. A lost
  response is not auto-retried because task creation is not idempotent. Server
  history has no task-list endpoint for recovery. Task creation times out after
  30 seconds with an explicit warning that it may have reached the server.
- Observer cleanup does not cancel execution. There is no cancellation API,
  follow-up steering, automatic conversational intent classifier or task retry
  engine. Ordinary chat is deliberately the default for trivial prompts.
- Existing edit/regenerate flows remain llama chat flows. SPEED response anchors
  suppress llama Continue/Regenerate buttons. Copied task links do not subscribe;
  submit a new SPEED prompt to start a new execution.
- Duration is based on available event timestamps, so truncated history yields
  a partial duration. Action counts are completed steps, not every raw event.
- A workflow with multiple independent final LLM outputs currently presents the
  last topological textual result. A richer result schema is outside this slice.
- Browser rendering, accessibility, service integration, builds and all tests
  remain unverified by execution. No generated assets were changed locally.
