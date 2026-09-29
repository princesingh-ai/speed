# SPEED authentication and model runtime

Source-only integration pass after 9fa1e36a181842ce6975478ce6dfbe854a625d9e.
No project, test, browser, model, build, MCP or Docker execution occurred on the Mac.

## Authentication modes

See [DEMO AUTH](phase1-demo-auth.md) for the current local hardcoded demo flow,
runtime flag, fixed identity, startup command and browser checks.

SPEED_DEMO_AUTH defaults to false, preserving the existing JWT login/me flow.
When true, the browser checks admin / admin-password locally and stores only
the username. It does not call login/me. Backend requests use the exact fixed
demo marker. Ownership, RBAC and consent remain enforced. The mode is read from
a public, uncached /api/v1/auth/config endpoint; credentials are never sent there.

The historical 87eb82e38ba8317a3de7a0f86e8e48383bb89a1c to
74777e2b146cf7260f4fe2bb4d2c173efce2a251 comparison confirmed those demo credentials
and the local-login concept. No Snap branding or unrelated historical code was
restored. SPEED branding and the working /login -> /#/login redirect remain.

## Actual model architecture

| Model | Role | Runtime | Default |
| --- | --- | --- | --- |
| gemma-reasoning | Chat, reasoning, coding and Phase 1 planning/analysis | llama-server | http://127.0.0.1:8080 |
| laya | Classifies chat tasks as coding/reasoning/general | laya.load inside the backend process | CUDA device, no HTTP endpoint or port |

The original Gemma artifact path was
`models/gemma4-12B/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`, under a hardcoded server
home directory. The same repository-relative artifact name is retained.
Laya expects the existing saved-model directory `models/laya`, loadable by
the installed laya package. No model files are tracked/present in this Mac
checkout. **Laya is configured but missing artifact locally.** Linux artifact
presence, CUDA compatibility and successful loading remain unverified.
The old Laya URL with port 0000 was a placeholder and has been removed.

Configuration is `config/models/models.yaml`; SPEED_MODELS_CONFIG may select
another file. Relative model paths resolve against the repository root, not CWD.
Overrides: SPEED_GEMMA_MODEL, SPEED_GEMMA_ENDPOINT, SPEED_LAYA_MODEL,
SPEED_LAYA_DEVICE. Supply these in the launching process environment (the model
router does not implicitly read .env). SPEED_LLAMA_SERVER selects the executable.
Existing CUDA_VISIBLE_DEVICES controls each process; no GPU index is invented.
Paths in config must identify actual operator-provisioned artifacts.

Gemma is the only configured generative model. It serves all three chat task
categories; Laya is never exposed as a selectable chat model. Laya loads lazily
on the first ordinary chat analysis, in a serialized worker thread in the backend.
Starting llama-server cannot start Laya. Agent planning directly selects Gemma
and does not invoke the chat classifier. No embedding or extra generative model
is actually configured.

Missing Laya gives an explicit deterministic_general fallback log and
X-SPEED-Task-Analysis: deterministic_fallback on chat responses. Load/prediction
failure remains failed until backend restart, avoiding repeated expensive loads.
Missing artifacts can be provisioned then retried. Successful Laya use reports
mode laya. A present directory alone never means healthy.

GET /api/v1/models/health requires a JWT or the fixed marker in enabled demo mode. It reports identifier, purpose,
runtime kind, endpoint, artifact existence and availability. Laya distinguishes
missing_artifact, not_loaded, loading, healthy, failed. Gemma probes /health and
/v1/models with bounded timeouts, rejecting unavailable/mismatched models.
The served ID is the GGUF basename, matching vendored llama-server behavior.
The router checks health before selection; inference failure is still possible
after a successful probe and is logged. No response is fabricated.
Ordinary chat returns 503 if no model is available; Phase 1 retains its explicitly
marked deterministic/mock fallback. The model list describes configuration,
while the authenticated health endpoint reports observed availability.

## Startup and observability

`PYTHONPATH=backend uv run python -m app.model_startup --validate-only`
validates artifacts without starting a service. Without --validate-only it
replaces itself with the selected configured llama-server process. It prints
artifact and starting states, never claims ready before a health probe.
Laya is loaded by the separately started backend, not this helper.
The helper uses the same YAML/environment resolution as ModelRouter.
Pass existing server GPU/context options after `--`; do not override model,
alias, host or port with conflicting options. HTTPS termination remains at
the deployment gateway. Default NGINX upstream is 8080; update its upstream
explicitly if changing SPEED_GEMMA_ENDPOINT.

Backend startup logs configured runtime/endpoint and missing/present artifacts.
speed.auth logs success with a stable user ID or generic failure.
speed.models logs health, router/planner selection, Laya load/fallback and
inference failures. Existing speed.execution events cover task creation,
planner mode, MCP, sandbox and artifacts with IDs/statuses; speed.websocket
includes connect/disconnect and replay cursor/count. Logs go to the process
stderr/console (or the existing supervisor's capture). No prompts, passwords,
tokens, auth headers, document contents or raw subprocess output are logged.

NGINX logs are infrastructure/nginx/logs/access.log and logs/error.log under
that prefix. Access entries include method, URI path, status, upstream status
and elapsed time, without query strings or authorization headers. WebSocket
upgrades appear as 101 entries when connections close. Keep the real deployment
prefix when testing/reloading; no systemd unit names are assumed.

## MCP decoding

The old adapter rejected every success without structured_content. The MCP v2
contract allows content blocks as well as structured output; the bundled plain
dict tools can return a JSON TextContent block. The adapter accepts a structured
object or exactly one bounded JSON text block decoding to an object. It rejects
error-flagged results, malformed JSON, non-objects and unsupported/ambiguous
blocks. Mapped errors are raised after normal client-context exit; transport and
cleanup errors retain their original semantics. No arithmetic is hardcoded.
The real stdio integration test still requires calculator 42, successful search,
invalid-operation RuntimeError, two mcp.completed events and one mcp.failed.

References: [SDK client contract](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)
and [direct CallToolResult examples](https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/servers/direct_call_tool_result.py).
The manifest specifies mcp>=2,<3, not an exact pin; the tracked uv.lock predates
that dependency. The Linux installed version cannot be established from this
Mac source checkout. No package/lockfile changes were made in this pass.

## Server validation sequence

Linux only, after a safe fast-forward pull of feature/phase1-agent-orchestration.
Preserve local deployment/lockfile changes. Use the existing prepared dependency
environment; reconcile the pre-existing stale Python lock on the authorized
server separately if necessary. Commands below assume bash, the repository root,
the existing llama.cpp/build CMake cache, and the repository NGINX prefix.

1. Backend tests:
   `uv run pytest tests/phase1`
2. Svelte check:
   `npm --prefix llama.cpp/tools/ui run check`
3. Unit tests:
   `npm --prefix llama.cpp/tools/ui run test:unit -- --run tests/unit/router.service.test.ts tests/unit/speed-api.test.ts tests/unit/speed-trace.test.ts tests/unit/speed-messages.test.ts`
4. The earlier client run was blocked by absent Chromium, not an application
   assertion. If needed, install the browser matching the installed Playwright:
   `(cd llama.cpp/tools/ui && ./node_modules/.bin/playwright install chromium)`
   If Linux browser libraries are missing, the operator can instead use
   `./node_modules/.bin/playwright install --with-deps chromium` in that directory.
   Offline deployments need an approved matching browser/dependency cache.
5. Client tests:
   `npm --prefix llama.cpp/tools/ui run test:client -- --run tests/client/speed-demo-auth.svelte.test.ts tests/client/speed-auth.svelte.test.ts tests/client/speed-activity.svelte.test.ts tests/client/speed-stabilization.svelte.test.ts`
6. UI build:
   `npm --prefix llama.cpp/tools/ui run build`
7. Rebuild the existing configured llama-server, retaining cached GPU/toolchain options:

   ```sh
   cmake -S llama.cpp -B llama.cpp/build -DLLAMA_USE_PREBUILT_UI=OFF
   cmake --build llama.cpp/build --target llama-server --parallel
   ```

   Substitute the actual existing build directory if different. The UI is embedded
   into the binary; building only the frontend does not update the running server.
8. Stop the prior llama-server through its existing supervisor/terminal, then in
   a model terminal export the actual artifact overrides if defaults differ:

   ```sh
   # Use actual existing paths; do not download or invent an artifact.
   export SPEED_GEMMA_MODEL="/absolute/path/to/existing/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
   export SPEED_LAYA_MODEL="/absolute/path/to/existing/laya"
   PYTHONPATH=backend uv run python -m app.model_startup --validate-only
   PYTHONPATH=backend uv run python -m app.model_startup -- --n-gpu-layers 99
   ```

   Retain the deployment's actual GPU/context flags; 99 requests full GPU
   offload for this model and requires sufficient memory. Set SPEED_LLAMA_SERVER
   if the existing binary lives elsewhere. Do not run a duplicate process on 8080.
9. In a backend terminal, export the same model overrides and existing
   SPEED_JWT_SECRET without printing it. Restart the existing process:
   `SPEED_DEMO_AUTH=true CUDA_VISIBLE_DEVICES=1 PYTHONPATH=backend uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
   One worker is required for the in-memory task registry. Laya loads on first chat.
10. In the gateway terminal:

    ```sh
    nginx -p "$PWD/infrastructure/nginx/" -c conf/nginx.conf -t
    nginx -p "$PWD/infrastructure/nginx/" -c conf/nginx.conf -s reload
    ```

    If no NGINX instance is running, use the same command without -s reload to
    start it. Retain the deployment's actual prefix/config if different.
11. Open http://SERVER:9100/login, accept the rebuilt PWA update if offered, and
    sign in as admin with the development password above. Expect SPEED at
    /#/login, invalid-password inline errors, then chat at /#/. Revisit /login:
    expect chat without a loop. Send a normal chat message; inspect model/fallback
    logs. Sign out and verify a protected chat URL returns to login.
12. Sign back in; enable SPEED agent without another login. Submit a document
    workflow, observe parallel dependency lanes and final result, download DOCX,
    and reopen the conversation. Verify MCP approval/search and denial separately;
    exercise Docker only if explicitly configured on this Linux server.
13. Verify model health using the fixed marker in demo mode:

    ```sh
    curl --fail --silent --show-error -H 'X-Speed-Demo-User: speed-demo-admin' \
      http://127.0.0.1:9100/api/v1/models/health
    ```

    Expect Gemma healthy after loading. Laya is healthy only after successful
    first-chat loading; otherwise the diagnostic reports its actual state.
    In real-auth mode use the existing JWT flow instead.

## Remaining operational limits

No local execution verification is claimed. Model artifacts/GPU capacity and
server processes are outside this source-only inspection. Hardcoded browser demo auth and its forgeable marker are not production security.
Real-auth mode retains the existing localStorage JWT session. Direct llama-server endpoints remain on loopback with their existing
API-key behavior; SPEED endpoints accept JWTs or the explicitly enabled fixed demo marker. Existing upstream
llama stream/lookup proxy exceptions are unchanged. Task/replay storage remains
in-memory. No Playwright binaries, model files, generated UI or dependency
installation output is part of this commit.
