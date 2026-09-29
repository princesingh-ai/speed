# Laya preload and SPEED Agent controls regression

History inspection found that 9fa1e36 already initialized TaskAnalyzer on the
first route call. The eager behavior was present in 9e2fc76: the module-level
RoutingService constructed TaskAnalyzer, whose constructor called laya.load
in-process with CUDA and a hardcoded model directory. Load failures propagated.
b6315f6 moved construction to route(); 14b6a53 and 9fa1e36 retained that change.
00ae1b8 retained lazy construction, added configurable paths/device, load status,
worker-thread analysis and an explicit deterministic fallback.

The restored lifecycle uses that same laya.load / TaskAnalyzer.model mechanism,
with current configured paths, during FastAPI lifespan startup before yield.
The existing RoutingService retains the analyzer. Requests never construct it.
No separate Laya process, port, model role or routing abstraction is introduced.
Missing artifacts report missing_artifact and explicit degraded operation;
other load failures abort startup. Provision/correct artifacts and restart.
The readiness log is "Laya analyzer ready in backend process", emitted after load.

The checkbox was not disabled by auth or model readiness. ChatScreen has a
pointer-events-none overlay; its pointer-events-auto class reaches only the
nested ChatForm. The sibling SpeedControls inherited pointer-events:none.
SpeedControls now opts into pointer-events-auto, as other interactive overlay
children do. Its existing settings disclosure opens when enabled, so the Workflow
selector and options appear immediately. Disabling removes them.

Demo login, fixed identity, branding, consent, artifacts, MCP and Gemma
configuration/launch behavior are unchanged.

Focused tests written, not executed:

- tests/phase1/test_model_runtime.py: lifespan preload, retained analyzer,
  no request-time initialization, missing artifacts and load failures.
- tests/client/speed-controls.svelte.test.ts: real computed CSS/hit testing under
  the overlay gate, local demo login, toggle state, selector visibility and no
  second credential exchange.
- tests/phase1/conftest.py supplies a missing synthetic Laya path to API tests,
  so tests never accidentally preload an operator's real GPU artifact.

## Minimal Linux validation

1. Pull on the existing branch:
   `git pull --ff-only origin feature/phase1-agent-orchestration`
2. Restart the existing backend with its existing model path and secret settings:

   ```sh
   SPEED_DEMO_AUTH=true CUDA_VISIBLE_DEVICES=1 PYTHONPATH=backend \
     uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

   Before any chat, expect Laya loading then ready in backend process before
   application startup completes. A missing-artifact warning is degraded status,
   not successful preload; correct SPEED_LAYA_MODEL and restart in that case.
3. UI source changed. Build and embed it using the deployment's existing build:

   ```sh
   npm --prefix llama.cpp/tools/ui run build
   cmake -S llama.cpp -B llama.cpp/build -DLLAMA_USE_PREBUILT_UI=OFF
   cmake --build llama.cpp/build --target llama-server --parallel
   ```

   Substitute the actual existing build directory if different. Restart the
   existing llama-server using exactly its existing Gemma/reasoning/draft/mmproj/
   context/port arguments. Do not replace its launch command with a new one.
4. Open http://SERVER:9100/login, accept the UI update if offered, and sign in
   locally with admin / admin-password. Click SPEED Agent: it must check and
   immediately show Workflow with Document/MCP/Coding plus options. Uncheck it:
   controls must disappear. No second login, JWT exchange or health-page step.

No full Phase 1 suite rerun is requested. No runtime, model, build or tests were
executed on the local Mac.
