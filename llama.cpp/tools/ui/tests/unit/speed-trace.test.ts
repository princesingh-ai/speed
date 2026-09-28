import { describe, expect, it } from 'vitest';
import { activityRows, graphEdges, lanesFor, mergeEvents, safePath } from '../../src/lib/speed/trace';
import { belongsToMessage } from '../../src/lib/speed/types';
import { event, snapshot } from './speed-fixtures';

describe('execution activity', () => {
	it('orders by sequence, deduplicates replay, and excludes another task', () => {
		const result = mergeEvents('task-a', [event(2)], [event(3), event(1), event(2), event(4, { task_id: 'task-b' })]);
		expect(result.map(e => e.sequence)).toEqual([1, 2, 3]);
	});

	it('updates one operation, displays relative paths/edit counts, and excludes contents', () => {
		const state = snapshot([{ id: 'read' }]);
		const rows = activityRows(state, [event(1), event(2, { event_type: 'file.updated', metadata: {
			path: 'reports/note.txt', lines_added: 18, lines_removed: 3, content: 'PRIVATE', token: 'SECRET'
		} }), event(3, { event_type: 'step.completed', status: 'completed', duration_ms: 22 })]);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toMatchObject({ title: 'Edit reports/note.txt', status: 'completed', duration: 22 });
		expect(rows[0].details).toContain('+18 / -3');
		expect(JSON.stringify(rows)).not.toMatch(/PRIVATE|SECRET/);
	});

	it('shows file reads and preserves snapshot state when replay is older', () => {
		const state = snapshot([{ id: 'read', status: 'completed' }], { last_sequence: 8 });
		const rows = activityRows(state, [event(1), event(2, { event_type: 'file.read', metadata: { path: 'report.txt', size: 42 } })]);
		expect(rows[0]).toMatchObject({ title: 'Read report.txt', status: 'completed' });
		expect(rows[0].details).toContain('42 bytes');
	});

	it.each(['/private/report', '../secret', 'a/../../secret', 'C:\\secret', '\\server\\share', 'bad\npath'])(
		'hides unsafe path %s', path => expect(safePath(path)).toBeUndefined()
	);

	it('keeps linear work in one lane and draws only dependency edges', () => {
		const state = snapshot([{ id: 'a' }, { id: 'b', dependencies: ['a'] }, { id: 'c', dependencies: ['b'] }]);
		expect([...lanesFor(state.steps).values()]).toEqual([0, 0, 0]);
		const rows = activityRows(state, []);
		expect(graphEdges(rows)).toHaveLength(2);
		expect(graphEdges(activityRows(snapshot([{ id: 'a' }]), []))).toEqual([]);
	});

	it('branches independent work and joins real fan-in without depending on event timing', () => {
		const state = snapshot([{ id: 'root' }, { id: 'a', dependencies: ['root'] },
			{ id: 'b', dependencies: ['root'] }, { id: 'join', dependencies: ['a', 'b'] }]);
		const lanes = lanesFor(state.steps);
		expect(lanes.get('a')).not.toBe(lanes.get('b'));
		expect(lanes.get('join')).toBe(lanes.get('a'));
		const rows = activityRows(state, []);
		expect(graphEdges(rows)).toHaveLength(4);
		expect(graphEdges(rows).some(path => path.includes('26'))).toBe(true);
		expect(lanesFor(snapshot([{ id: 'a' }, { id: 'b' }]).steps).get('b')).toBe(1);
	});

	it('restores waiting, sandbox, MCP and mock details without command output', () => {
		const events = [event(1, { event_type: 'step.waiting', status: 'waiting', metadata: {
			consent_id: 'consent-1', permission: 'sandbox.execute', resource: 'sandbox:python'
		} }), event(2, { event_type: 'sandbox.started', title: 'Sandbox: python calculation', is_mock: true }),
		 event(3, { event_type: 'sandbox.completed', metadata: { exit_code: 0, stdout: 'PRIVATE' } })];
		const rows = activityRows(snapshot([{ id: 'read' }]), events);
		expect(rows[0]).toMatchObject({ status: 'waiting', consentId: 'consent-1', mock: true });
		expect(rows[0].details).toContain('Exit 0');
		expect(JSON.stringify(rows)).not.toContain('PRIVATE');
		const mcp = activityRows(undefined, [event(1, { event_type: 'mcp.started', metadata: { tool_name: 'search_internal_docs' } }),
			event(2, { event_type: 'mcp.completed', metadata: { result_count: 3 } })]);
		expect(mcp[0].title).toBe('MCP: search_internal_docs');
		expect(mcp[0].details).toContain('3 results');
	});

	it('requires both conversation and user-turn identity, including copied messages', () => {
		const link = { conversationId: 'a', userMessageId: 'u', ownerId: 'owner', taskId: 'task-a' };
		expect(belongsToMessage(link, { convId: 'a', parent: 'u' })).toBe(true);
		expect(belongsToMessage(link, { convId: 'b', parent: 'u' })).toBe(false);
		expect(belongsToMessage(link, { convId: 'a', parent: 'v' })).toBe(false);
	});
});
