# Phase 1 in the existing chat

This integration uses the vendored Svelte UI under `llama.cpp/tools/ui` on
`feature/phase1-agent-orchestration`. It adds no UI dependencies and creates no
second conversation system. `/phase1/` remains a developer inspection/demo view.

## Use

Ordinary chat remains the default, including small questions, manual model
selection, existing tool calls, MCP attachments and the llama agentic loop.
Sign in once through **Sign in to SPEED**, then enable **SPEED agent** above the
composer. Open **Agent settings** and select Document, Document + local MCP, or
Coding sandbox. Chat and agent APIs share the backend-verified JWT. The token is
stored under `SPEED.auth.accessToken`; refresh verifies it through `/api/v1/auth/me`.
Logout and expired-session responses clear both chat and agent authentication.
The local-agent label describes execution on the server workspace, not an
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
stored in the browser, just like existing chat history. The separate auth storage
key contains the verified SPEED JWT; task messages never contain tokens.

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

Use [the SPEED authentication and model runbook](phase1-runtime.md) for the current
ordered validation/build/startup commands. Preserve deployment changes before a
fast-forward pull. No commands in that runbook were executed on this Mac.

## Stabilization: login, MCP cleanup and chat types

The UI uses `kit.router.type: 'hash'`, not history routing. `/login` is a real
Svelte route, but the browser must enter it as `/#/login`. llama-server registers
`/`, `/index.html` and embedded assets; it does not provide an arbitrary path
fallback. The gateway now handles exactly `/login` with a temporary redirect to
`/#/login`. The browser then requests `/` for the application shell, and Svelte
renders the login page from the fragment. Keeping the literal `/login` URL would
require changing the routing architecture; this fix retains the existing router.

Authentication navigation now uses the same hash-route constants as chat.
The layout decides redirects from authentication state and Svelte route identity,
not `pathname` (which stays `/` across hash routes). While authentication is
checking it does not redirect. An unauthenticated protected route enters
`#/login`; successful login or an already-authenticated login route enters `#/`.
Settled public/protected routes do not redirect. The subsequent unified SPEED
login uses backend JWT authentication; ownership and RBAC remain authoritative.

| Gateway route | Behavior |
| --- | --- |
| `/` | Existing llama-server application shell |
| `/login` | HTTP 302 to `/#/login`; Svelte renders login after loading `/` |
| `/v1/*` | Existing SPEED proxy, with existing llama stream/lookup exceptions |
| `/api/v1/*` | Existing SPEED proxy and task ownership checks |
| WebSocket endpoints | Existing `/api/v1/` upgrade forwarding |
| Static/Svelte assets | Existing root proxy to llama-server |
| `/phase1/` | Existing developer/debug page through SPEED |

MCP returned tool errors, invalid payloads and discovery failures are
recorded inside the client context, then raised after clean context exit. This
prevents our intended `RuntimeError("MCP tool failed")` from being wrapped during
AnyIO task-group cleanup. Real stdio calls, structured-object and JSON text-block successes, and telemetry
remain intact. Transport, protocol and cleanup exceptions still propagate with
their original semantics; cleanup failures are not hidden by mapped tool errors.

The chat store keeps a stable local assistant after successful persistence and
checks its ID, role, conversation and parent before starting SPEED. A separate
optional reference supports error reporting. Failed/missing/mismatched creation
does not start a task. The assistant model control now honestly accepts an
optional regeneration callback: it shows a plain badge without one, and retains
selection/loading/regeneration when a callback is supplied.

### Server validation order (not executed on the Mac)

Follow [phase1-runtime.md](phase1-runtime.md#server-validation-sequence). The working
NGINX login redirect and hash-router tests remain unchanged. Client tests require
Playwright Chromium on the Linux validation machine.

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
