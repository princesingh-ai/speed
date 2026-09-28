import type { ExecutionEvent, Snapshot } from './types';

export interface ActivityRow {
	id: string;
	title: string;
	status: string;
	lane: number;
	dependencies: string[];
	details: string[];
	mock: boolean;
	duration?: number;
	consentId?: string;
	permission?: string;
	resource?: string;
}

export function safePath(value: unknown): string | undefined {
	if (typeof value !== 'string' || value.length > 500 || /^(?:[/\\]|[a-z]:)/i.test(value)
		|| value.split(/[/\\]/).includes('..') || /[\x00-\x1f]/.test(value)) return;
	return value;
}

/** Sequence is authoritative; replay cannot overwrite a newer event. */
export function mergeEvents(taskId: string, previous: ExecutionEvent[], incoming: ExecutionEvent[]) {
	const bySequence = new Map<number, ExecutionEvent>();
	for (const event of [...previous, ...incoming]) {
		if (event.task_id === taskId && Number.isSafeInteger(event.sequence) && event.sequence > 0
			&& !bySequence.has(event.sequence)) bySequence.set(event.sequence, event);
	}
	return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence).slice(-2000);
}

/** Allocate lanes in plan topological order, independent of event arrival order. */
export function lanesFor(steps: Snapshot['steps']) {
	const lanes = new Map<string, number>();
	const continued = new Set<string>();
	let nextLane = 0;
	while (lanes.size < steps.length) {
		const ready = steps.filter(s => !lanes.has(s.id) && s.dependencies.every(d => lanes.has(d)));
		if (!ready.length) break;
		for (const step of ready) {
			const parent = step.dependencies.find(d => !continued.has(d));
			lanes.set(step.id, parent ? lanes.get(parent)! : nextLane++);
			step.dependencies.forEach(d => continued.add(d));
		}
	}
	return lanes;
}

export function activityRows(snapshot: Snapshot | undefined, events: ExecutionEvent[]): ActivityRow[] {
	const steps = snapshot?.steps ?? [];
	const lanes = lanesFor(steps);
	const rows = new Map<string, ActivityRow>();
	const planning = events.filter(e => e.event_type.startsWith('plan.'));
	if (planning.length) {
		const last = planning[planning.length - 1];
		rows.set('planning', { id: 'planning', title: 'Planning', status: steps.length ? 'completed' : last.status,
			lane: 0, dependencies: [], details: planning.some(e => e.event_type === 'plan.fallback') ? ['Deterministic fallback'] : [],
			mock: planning.some(e => e.is_mock) });
	}
	for (const event of events) {
		if (!event.step_id) continue;
		const step = steps.find(s => s.id === event.step_id);
		let row = rows.get(event.step_id);
		if (!row) {
			row = { id: event.step_id, title: step?.title ?? event.title, status: step?.status ?? event.status,
				lane: lanes.get(event.step_id) ?? 0, dependencies: step?.dependencies ?? [], details: [], mock: false };
			rows.set(row.id, row);
		}
		if (event.event_type.startsWith('step.') && event.sequence > (snapshot?.last_sequence ?? 0)) row.status = event.status;
		row.mock ||= event.is_mock;
		if (event.duration_ms !== null) row.duration = event.duration_ms;
		const meta = event.metadata;
		const path = safePath(meta.path);
		if (event.event_type.startsWith('file.') && path) {
			const verb = event.event_type === 'file.read' ? 'Read' : event.event_type === 'file.created' ? 'Create' : 'Edit';
			row.title = `${verb} ${path}`;
		}
		const details: string[] = [];
		if (event.event_type === 'sandbox.started') row.title = event.title;
		if (event.event_type === 'mcp.started' && typeof meta.tool_name === 'string') row.title = `MCP: ${meta.tool_name.slice(0, 120)}`;
		if (event.event_type === 'model.started') details.push('Local model');
		if (event.event_type === 'artifact.created' && path) row.title = `Create ${path.split('/').at(-1)}`;
		if (typeof meta.tool_name === 'string') details.push(`Tool: ${meta.tool_name.slice(0, 120)}`);
		if (typeof meta.size === 'number') details.push(`${meta.size} bytes`);
		if (typeof meta.lines_added === 'number') details.push(`+${meta.lines_added} / -${Number(meta.lines_removed) || 0}`);
		if (typeof meta.exit_code === 'number') details.push(`Exit ${meta.exit_code}`);
		if (typeof meta.result_count === 'number') details.push(`${meta.result_count} results`);
		if (typeof meta.error_code === 'string') details.push(meta.error_code.slice(0, 100));
		if (event.event_type === 'model.fallback') details.push('Deterministic extract');
		row.details = [...new Set([...row.details, ...details])].slice(-8);
		if (event.event_type === 'step.waiting' && typeof meta.consent_id === 'string') {
			row.consentId = meta.consent_id;
			row.permission = typeof meta.permission === 'string' ? meta.permission : undefined;
			row.resource = safePath(meta.resource);
		}
	}
	// A truncated replay still shows every step's authoritative status/dependencies.
	for (const step of steps) {
		if (!rows.has(step.id)) rows.set(step.id, { id: step.id, title: step.title, status: step.status,
			lane: lanes.get(step.id) ?? 0, dependencies: step.dependencies, details: [], mock: false });
	}
	return [...rows.values()];
}

export function graphEdges(rows: ActivityRow[], rowHeight = 76) {
	return rows.flatMap((row, index) => row.dependencies.flatMap(id => {
		const source = rows.findIndex(r => r.id === id);
		if (source < 0) return [];
		const x1 = 10 + rows[source].lane * 16, y1 = source * rowHeight + 20;
		const x2 = 10 + row.lane * 16, y2 = index * rowHeight + 20;
		return [`M ${x1} ${y1} C ${x1} ${y1 + 32}, ${x2} ${y2 - 32}, ${x2} ${y2}`];
	}));
}
