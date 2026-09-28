# SPEED

Sovereign, on-premise AI workbench. Phase 1 adds a small, in-memory execution
vertical slice alongside the existing chat, task, security and native tool APIs.

`Planner → validated ExecutionPlan / TaskGraph → async Executor → existing
ToolRuntime / local inference / Docker sandbox / local MCP → real DOCX`

Open `/phase1/` for an event-driven Git-history-style dashboard. Its lanes represent
execution actions and dependencies, **not Git commits or repository branches**.

See [Phase 1 architecture, launch instructions and limitations](docs/phase1.md)
and [static validation record](docs/phase1-validation.md).

**This implementation was edited and reviewed without executing code locally.**
Tests, servers, models, Docker, MCP and document generation were not run. Dependency
requirements were declared in source; `uv.lock` must be regenerated on an authorized
execution machine before using a locked install.
