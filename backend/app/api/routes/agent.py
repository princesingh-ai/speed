import asyncio
import logging
from secrets import token_urlsafe
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.orchestration.models import ReviewRequest, StartRequest
from app.security.dependencies import get_current_user, require_permission
from app.security.models import Permission, User
from app.tools.builtin.filesystem_scope import filesystem_scope

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
logger = logging.getLogger("speed.websocket")


def owned(service, task_id, user):
    record = service.records.get(task_id)
    if record is None or record.task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    return record


@router.post("/tasks", status_code=202)
async def start(request: Request, body: StartRequest,
                user: User = Depends(require_permission(Permission.AGENT_EXECUTE))):
    try:
        record = request.app.state.agent.create(user, body)
    except PermissionError:
        raise HTTPException(403, "Agent execution denied")
    except ValueError as exc:
        raise HTTPException(429, str(exc))
    return {"task_id": record.task.id, "status": "created",
            "events_ws": f"/api/v1/agent/tasks/{record.task.id}/events"}


@router.get("/tasks/{task_id}")
async def snapshot(task_id: str, request: Request, user: User = Depends(get_current_user)):
    service = request.app.state.agent
    owned(service, task_id, user)
    return service.snapshot(task_id)


@router.get("/tasks/{task_id}/events")
async def history(task_id: str, request: Request, after_sequence: int = Query(0, ge=0),
                  user: User = Depends(get_current_user)):
    service = request.app.state.agent
    owned(service, task_id, user)
    events = service.bus.replay(task_id, after_sequence)
    return {"events": [e.model_dump(mode="json") for e in events],
            "snapshot": service.snapshot(task_id),
            "history_truncated": bool(events and events[0].sequence > after_sequence + 1)}


@router.post("/tasks/{task_id}/review")
async def review(task_id: str, body: ReviewRequest, request: Request,
                 user: User = Depends(require_permission(Permission.AGENT_EXECUTE))):
    service = request.app.state.agent
    owned(service, task_id, user)
    try:
        return service.review(task_id, user, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/tasks/{task_id}/ticket")
async def ticket(task_id: str, request: Request, user: User = Depends(get_current_user)):
    owned(request.app.state.agent, task_id, user)
    tickets = request.app.state.ws_tickets
    for key, value in list(tickets.items()):
        if value[2] < monotonic():
            tickets.pop(key, None)
    if len(tickets) >= 1000:
        raise HTTPException(429, "Too many pending WebSocket tickets")
    value = token_urlsafe(32)
    tickets[value] = (task_id, user.id, monotonic() + 30)
    return {"ticket": value}


@router.websocket("/tasks/{task_id}/events")
async def stream(websocket: WebSocket, task_id: str):
    # First frame authenticates using a single-use task-bound ticket. No JWT in URLs/logs.
    await websocket.accept()
    service = websocket.app.state.agent
    queue = None
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), 10)
        ticket_value = auth.get("ticket")
        if not isinstance(ticket_value, str):
            await websocket.close(code=4401)
            return
        ticket = websocket.app.state.ws_tickets.pop(ticket_value, None)
        record = service.records.get(task_id)
        if (ticket is None or ticket[0] != task_id or ticket[2] < monotonic()
                or record is None or record.task.user_id != ticket[1]):
            await websocket.close(code=4401)
            return
        after = auth.get("after_sequence", 0)
        if not isinstance(after, int) or after < 0 or after > service.bus.sequences[task_id]:
            await websocket.close(code=4400)
            return
        queue, replay = service.bus.subscribe(task_id, after)
        # Subscription, replay and snapshot capture are atomic on this event loop.
        initial = {"type": "snapshot", "snapshot": service.snapshot(task_id),
                   "events": [e.model_dump(mode="json") for e in replay],
                   "history_truncated": bool(replay and replay[0].sequence > after + 1)}
        await websocket.send_json(initial)
        logger.info("websocket connected task=%s replay_after=%s replay_count=%s", task_id, after, len(replay))
        while True:
            receiver = asyncio.create_task(websocket.receive())
            next_event = asyncio.create_task(queue.get())
            try:
                done, _ = await asyncio.wait({receiver, next_event}, timeout=20,
                                            return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    message = receiver.result()
                    if message["type"] == "websocket.disconnect":
                        break
                if next_event in done:
                    event = next_event.result()
                    if event is None:
                        await websocket.close(code=1013)
                        break
                    await websocket.send_json({"type": "event", "event": event.model_dump(mode="json")})
                if not done:
                    await websocket.send_json({"type": "heartbeat"})
            finally:
                for future in (receiver, next_event):
                    if not future.done():
                        future.cancel()
                await asyncio.gather(receiver, next_event, return_exceptions=True)
    except (WebSocketDisconnect, TimeoutError):
        pass
    except (ValueError, TypeError, AttributeError):
        await websocket.close(code=4400)
    finally:
        if queue is not None:
            service.bus.unsubscribe(task_id, queue)
        logger.info("websocket disconnected task=%s", task_id)


@router.get("/tasks/{task_id}/artifacts/{artifact_id}")
async def download(task_id: str, artifact_id: str, request: Request,
                   user: User = Depends(get_current_user)):
    record = owned(request.app.state.agent, task_id, user)
    artifact = next((a for a in record.artifacts if a["id"] == artifact_id), None)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    try:
        path = filesystem_scope.resolve_workspace_path(artifact["path"])
        root = filesystem_scope.resolve_workspace_path(f"outputs/tasks/{task_id}")
        path.relative_to(root)
    except (ValueError, PermissionError):
        raise HTTPException(404, "Artifact not found")
    if not path.is_file():
        raise HTTPException(404, "Artifact no longer available")
    return FileResponse(path, filename=artifact["name"],
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Cache-Control": "no-store"})
