import type { ExecutionEvent, Snapshot, Step } from '../../src/lib/speed/types';

export function event(sequence: number, changes: Partial<ExecutionEvent> = {}): ExecutionEvent {
	return { event_id: `e${sequence}`, sequence, task_id: 'task-a', step_id: 'read',
		event_type: 'step.started', status: 'running', title: 'Read report',
		timestamp: `2026-01-01T00:00:${String(sequence).padStart(2, '0')}Z`,
		duration_ms: null, metadata: {}, is_mock: false, ...changes };
}

export function snapshot(steps: Partial<Step>[] = [], changes: Partial<Snapshot> = {}): Snapshot {
	return { task_id: 'task-a', status: 'running', steps: steps.map((step, i) => ({
		id: `step-${i}`, title: `Step ${i}`, kind: 'llm', dependencies: [], status: 'pending', ...step
	})), artifacts: [], last_sequence: 0, has_mock: false, summary: '', final_response: '',
		planner_mode: 'local_model', ...changes };
}
