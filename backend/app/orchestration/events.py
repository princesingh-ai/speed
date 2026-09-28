"""Single event-loop bus. No awaits between sequence allocation and publication."""
import asyncio
import logging
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass

from app.orchestration.models import ExecutionEvent

logger = logging.getLogger("speed.execution")
SAFE_METADATA = {"path", "size", "created", "lines_added", "lines_removed", "tool_name",
                 "dependencies", "source_lanes", "consent_id", "permission", "resource",
                 "exit_code", "stdout_bytes", "stderr_bytes", "result_count", "error_code",
                 "planner_mode", "artifact_id", "mock_source", "timed_out"}


class EventBus:
    def __init__(self, history_limit=2000):
        self.history_limit = history_limit
        self.history = defaultdict(lambda: deque(maxlen=history_limit))
        self.sequences = defaultdict(int)
        self.subscribers = defaultdict(set)

    def emit(self, task_id, event_type, title, status="completed", **kwargs):
        metadata = kwargs.pop("metadata", {})
        metadata = {k: v for k, v in metadata.items() if k in SAFE_METADATA}
        self.sequences[task_id] += 1
        event = ExecutionEvent(task_id=task_id, sequence=self.sequences[task_id],
                               event_type=event_type, title=title, status=status,
                               metadata=metadata, **kwargs)
        self.history[task_id].append(event)
        for queue in tuple(self.subscribers[task_id]):
            if queue.full():
                # Explicit gap marker; the WS consumer closes and client replays.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.subscribers[task_id].discard(queue)
            else:
                queue.put_nowait(event)
        logger.info("execution task=%s step=%s sequence=%s type=%s status=%s",
                    task_id, event.step_id, event.sequence, event_type, status)
        return event

    def replay(self, task_id, after=0):
        return [e for e in self.history[task_id] if e.sequence > after]

    def subscribe(self, task_id, after=0):
        queue = asyncio.Queue(maxsize=256)
        self.subscribers[task_id].add(queue)
        return queue, self.replay(task_id, after)

    def unsubscribe(self, task_id, queue):
        self.subscribers[task_id].discard(queue)


@dataclass
class Trace:
    bus: EventBus
    task_id: str
    step_id: str | None = None
    lane_id: int = 0
    parent_event_id: str | None = None
    is_mock: bool = False

    def emit(self, event_type, title, status="completed", **kwargs):
        return self.bus.emit(self.task_id, event_type, title, status,
                             step_id=self.step_id, lane_id=self.lane_id,
                             parent_event_id=self.parent_event_id,
                             is_mock=kwargs.pop("is_mock", self.is_mock), **kwargs)


current_trace: ContextVar[Trace | None] = ContextVar("execution_trace", default=None)
