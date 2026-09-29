import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { downloadArtifact, request, startTask, watchTask } from '../../src/lib/speed/api';
import { event, snapshot } from './speed-fixtures';

const auth = vi.hoisted(() => ({ credential: 'jwt', handleUnauthorized: vi.fn() }));
vi.mock('$lib/stores/auth.svelte', () => ({ authStore: auth }));

class Socket {
	static instances: Socket[] = [];
	onopen?: () => void;
	onmessage?: (event: { data: string }) => void;
	onclose?: () => void;
	onerror?: () => void;
	send = vi.fn();
	close = vi.fn(() => this.onclose?.());
	constructor(public url: URL) { Socket.instances.push(this); }
	frame(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
}

const observer = () => ({ snapshot: vi.fn(), events: vi.fn(), connection: vi.fn(), error: vi.fn() });
const response = (value: unknown) => new Response(JSON.stringify(value));

beforeEach(() => {
	auth.handleUnauthorized.mockClear();
	vi.useFakeTimers();
	Socket.instances = [];
	vi.stubGlobal('WebSocket', Socket);
	vi.stubGlobal('window', { location: { origin: 'https://speed.example', protocol: 'https:' } });
	vi.stubGlobal('fetch', vi.fn(async () => response({ ticket: 'one-use-ticket' })));
});

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('SPEED transport', () => {
	it('uses a first-frame ticket, replays its cursor and closes on unmount', async () => {
		const callbacks = observer();
		const stop = watchTask('task-a', 'private-jwt', callbacks);
		await vi.advanceTimersByTimeAsync(0);
		const first = Socket.instances[0];
		expect(first.url.href).toBe('wss://speed.example/api/v1/agent/tasks/task-a/events');
		first.onopen?.();
		expect(first.send).toHaveBeenCalledWith(JSON.stringify({ ticket: 'one-use-ticket', after_sequence: 0 }));
		first.frame({ type: 'snapshot', snapshot: snapshot([], { last_sequence: 2 }), events: [event(2), event(1)] });
		expect(callbacks.events.mock.calls[0][0].map((e: { sequence: number }) => e.sequence)).toEqual([1, 2]);
		first.frame({ type: 'event', event: event(2) });
		expect(callbacks.events.mock.lastCall?.[0]).toEqual([]);
		first.close();
		await vi.advanceTimersByTimeAsync(1000);
		const second = Socket.instances[1];
		second.onopen?.();
		expect(second.send).toHaveBeenCalledWith(JSON.stringify({ ticket: 'one-use-ticket', after_sequence: 2 }));
		stop();
		await vi.advanceTimersByTimeAsync(60000);
		expect(Socket.instances).toHaveLength(2);
	});

	it('does not poll a healthy stream, excludes foreign events, and recovers sequence gaps', async () => {
		const callbacks = observer();
		const stop = watchTask('task-a', 'jwt', callbacks);
		await vi.advanceTimersByTimeAsync(0);
		const ws = Socket.instances[0];
		ws.frame({ type: 'snapshot', snapshot: snapshot([], { last_sequence: 1 }), events: [event(1)] });
		ws.frame({ type: 'event', event: event(2, { task_id: 'task-b' }) });
		await vi.advanceTimersByTimeAsync(20000);
		ws.frame({ type: 'heartbeat' });
		expect(fetch).toHaveBeenCalledTimes(1);
		ws.frame({ type: 'event', event: event(3) });
		expect(ws.close).toHaveBeenCalled();
		stop();
	});

	it('restores a terminal snapshot, reports truncated replay, and ends the connection', async () => {
		const callbacks = observer();
		watchTask('task-a', 'jwt', callbacks);
		await vi.advanceTimersByTimeAsync(0);
		const ws = Socket.instances[0];
		ws.frame({ type: 'snapshot', snapshot: snapshot([], { status: 'completed', last_sequence: 50, final_response: 'Actual result' }),
			events: [event(50)], history_truncated: true });
		expect(callbacks.events).toHaveBeenCalledWith([event(50)], true);
		expect(callbacks.snapshot.mock.lastCall?.[0].final_response).toBe('Actual result');
		expect(ws.close).toHaveBeenCalled();
	});

	it.each([401, 403, 404])('stops on HTTP %s without reconnect loops', async status => {
		vi.mocked(fetch).mockResolvedValue(new Response('', { status }));
		const callbacks = observer();
		watchTask('task-a', 'jwt', callbacks);
		await vi.advanceTimersByTimeAsync(60000);
		expect(callbacks.error).toHaveBeenCalled();
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(Socket.instances).toHaveLength(0);
	});

	it('does not let a late lifecycle response replace the final result', async () => {
		let resolveOlder: (response: Response) => void = () => {};
		vi.mocked(fetch)
			.mockResolvedValueOnce(response({ ticket: 'ticket' }))
			.mockImplementationOnce(() => new Promise(resolve => { resolveOlder = resolve; }))
			.mockResolvedValueOnce(response(snapshot([], { status: 'completed', last_sequence: 2, final_response: 'Final' })));
		const callbacks = observer();
		watchTask('task-a', 'jwt', callbacks);
		await vi.advanceTimersByTimeAsync(0);
		const ws = Socket.instances[0];
		ws.frame({ type: 'event', event: event(1, { event_type: 'plan.created' }) });
		ws.frame({ type: 'event', event: event(2, { event_type: 'task.completed' }) });
		await vi.advanceTimersByTimeAsync(0);
		resolveOlder(response(snapshot([], { last_sequence: 1 })));
		await vi.advanceTimersByTimeAsync(0);
		expect(callbacks.snapshot).toHaveBeenCalledTimes(1);
		expect(callbacks.snapshot.mock.lastCall?.[0].final_response).toBe('Final');
	});

	it('bounds consecutive connection failures and reports an actionable error', async () => {
		vi.mocked(fetch).mockRejectedValue(new TypeError('Offline'));
		const callbacks = observer();
		watchTask('task-a', 'jwt', callbacks);
		await vi.advanceTimersByTimeAsync(100000);
		expect(fetch).toHaveBeenCalledTimes(7);
		expect(callbacks.error.mock.lastCall?.[0]).toContain('Reconnect');
	});

	it('posts the selected workflow exactly once and preserves authorization', async () => {
		vi.mocked(fetch).mockRejectedValue(new TypeError('Network lost'));
		await expect(startTask('Review', { flow: 'document', demo_mode: true, input_path: 'report.txt' }, 'jwt')).rejects.toThrow();
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch).toHaveBeenCalledWith('/api/v1/agent/tasks', expect.objectContaining({
			method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer jwt' }),
			body: JSON.stringify({ objective: 'Review', flow: 'document', demo_mode: true, input_path: 'report.txt' })
		}));
	});

	it('uses authenticated artifact IDs, never imported download URLs', async () => {
		const click = vi.fn();
		const anchor = { href: '', download: '', click };
		vi.stubGlobal('document', { createElement: vi.fn(() => anchor) });
		vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:safe');
		const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
		const artifact = { id: 'artifact-1', name: 'note.docx', size: 10, is_mock: false, download_url: 'https://evil.example/secret' };
		await downloadArtifact('task-a', artifact, 'jwt');
		expect(fetch).toHaveBeenCalledWith('/api/v1/agent/tasks/task-a/artifacts/artifact-1', expect.objectContaining({
			headers: { Authorization: 'Bearer jwt' }
		}));
		expect(click).toHaveBeenCalledOnce();
		await vi.advanceTimersByTimeAsync(1000);
		expect(revoke).toHaveBeenCalledWith('blob:safe');
	});

	it('consent requires an explicit authenticated POST', async () => {
		await request('permissions/consent-1/deny', 'jwt', { method: 'POST' });
		expect(fetch).toHaveBeenCalledWith('/api/v1/permissions/consent-1/deny', expect.objectContaining({ method: 'POST' }));
	});

	it.each(['..', '../secret', '/absolute', 'https://evil.example'])('rejects imported artifact path %s', async id => {
		await expect(downloadArtifact('task-a', { id, name: 'note.docx', size: 1, is_mock: false }, 'jwt')).rejects.toThrow('Invalid SPEED resource ID');
		expect(fetch).not.toHaveBeenCalled();
	});
});
