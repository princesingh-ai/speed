# DEMO AUTH

This is development-only authentication, not production security.

## Login

Credentials: username **admin**, password **admin-password**.

With SPEED_DEMO_AUTH=true the integrated SPEED UI validates these exact values
locally and immediately enters /#/. It stores only admin under SPEED.auth.demoUser,
never the password or a JWT. Wrong credentials show "Invalid username or password."
Refresh restores the local session. Logout removes it and returns to /#/login.
The existing SPEED design remains, with a subtle Demo label.

The UI reads GET /api/v1/auth/config once during initialization, with no credentials
and no caching. This runtime setting avoids separate frontend/backend build flags.
Demo login never calls POST /api/v1/auth/login or GET /api/v1/auth/me.
A configuration lookup failure fails closed and allows a reload/retry; it does not
silently switch to JWT login. The backend must still be reachable for configuration
and the workbench APIs. This is not an offline frontend-only application.

## Backend gate and principal

SPEED_DEMO_AUTH defaults to false. When true, only the exact header
X-Speed-Demo-User: speed-demo-admin resolves to the existing User model:
id speed-demo-admin, username admin, roles [admin]. Unknown marker values are
rejected. Absent markers still require a valid JWT; endpoints are not public.

The integrated chat and agent transport share this marker. Task ownership,
WebSocket ticket issuance, consent, artifact access and model diagnostics all
resolve to that same principal. There is no second login or token input.
Existing ordinary llama API-key headers remain available.

Demo authentication does NOT auto-approve tools, MCP or sandbox execution.
Existing RBAC/policies and explicit consent remain enforced. WebSockets still
require expiring, single-use task-bound tickets. Foreign task access and artifact
downloads remain denied, and artifact registration/path validation is unchanged.

When SPEED_DEMO_AUTH=false, demo headers are rejected and local demo storage is
discarded on UI initialization. Existing login/me endpoints, JWT verification,
RBAC and ownership checks remain. The prior JWT tests remain in the suite.
The standalone /phase1 debug page retains its existing JWT sign-in; use integrated
chat for the new demo flow.

The browser credential check is only a UX demonstration. Anyone who can reach a
demo-enabled backend can forge the public marker. All demo browsers intentionally
share the same identity and its tasks; isolation remains between that identity and
other real principals. Use only in a controlled development environment.

## Server startup

Keep the deployment's existing SPEED_JWT_SECRET and model configuration. The JWT
implementation remains available, so its existing required secret setting remains.
No new dependencies or separate frontend build-time flag are needed.

```sh
SPEED_DEMO_AUTH=true \
CUDA_VISIBLE_DEVICES=1 \
PYTHONPATH=backend \
uv run uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

Reload is for development and resets the in-memory task registry. Do not use
multiple workers. Startup logs the enabled mode and fixed principal, never
passwords, JWTs or authorization headers. To return to real auth, restart with
SPEED_DEMO_AUTH=false and refresh the browser.

Deploy the updated UI using the existing Linux build/embed procedure in
[the runtime runbook](phase1-runtime.md). An old embedded UI will still attempt
JWT login; restarting only the backend cannot replace that browser code.
The model startup helper, Gemma checks, Laya fallback and MCP decoding are unchanged.

## Validation on Linux only

Backend regressions: `uv run pytest tests/phase1`.
Client regressions include `tests/client/speed-demo-auth.svelte.test.ts` and the
existing `speed-auth.svelte.test.ts` JWT tests. Follow the runtime runbook's
Svelte/unit/client/build sequence; no tests or builds ran on this Mac.

1. Open http://SERVER:9100/login and accept the rebuilt PWA update if offered.
2. Expect SPEED and a subtle Demo label at /#/login.
3. Try a wrong username/password: expect the inline error and no navigation.
4. Enter admin / admin-password: expect immediate chat at /#/.
5. In Network, /api/v1/auth/config is expected, but auth/login and auth/me must
   be absent. Browser storage must contain only the demo username, no password.
6. Refresh: remain signed in. Revisit /login: return to chat without a loop.
7. Logout: return to login; opening /#/ while logged out must remain protected.
8. Sign in again, enable SPEED Agent, choose Document and demonstration analysis,
   and submit "Review the inspection report and create an approval note."
   Expect task creation with X-Speed-Demo-User, no Authorization JWT and no second
   login. Inspect the inline trace, final response and registered DOCX download.
9. Reopen the conversation. Verify replay and artifacts remain associated with
   the same identity. Try Document + local MCP and verify explicit consent is
   still required; test rejection as well as approval.
10. With the backend demo flag disabled, the marker must return 401 and the
    refreshed UI must return to the normal JWT authentication flow.

Model diagnostics in demo mode (Linux only):

```sh
curl --fail --silent --show-error \
  -H 'X-Speed-Demo-User: speed-demo-admin' \
  http://127.0.0.1:9100/api/v1/models/health
```

Tests cover local credentials, no credential API exchange, navigation, refresh,
logout, fixed headers, disabled mode, JWT preservation, task-bound tickets,
artifact ownership and consent. These tests were written but not executed locally.
