import type { Artifact, ExecutionEvent, Snapshot, TaskOptions } from './types';
import { terminal } from './types';
import { speedAuthHeaders } from './auth';

export class SpeedError extends Error {
	constructor(public status: number) {
		super(status === 401 ? 'Sign in to SPEED again.' : status === 404
			? 'Task unavailable. It may belong to another user or the server may have restarted.'
			: status === 403 ? 'This action is not permitted.' : `SPEED request failed (${status}).`);
	}
}

async function checkResponse(response: Response, token: string) {
	if (response.status === 401) {
		const { authStore } = await import('$lib/stores/auth.svelte');
		if (authStore.credential === token) authStore.handleUnauthorized();
	}
	if (!response.ok) throw new SpeedError(response.status);
}

export async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
	const response = await fetch(`/api/v1/${path}`, {
		...init, cache: 'no-store', credentials: 'same-origin',
		signal: init.signal ?? AbortSignal.timeout(30000),
		headers: { 'Content-Type': 'application/json', ...speedAuthHeaders(token) }
	});
	await checkResponse(response, token);
	return response.json();
}

function routeId(id: string) {
	if (!/^[a-zA-Z0-9_-]{1,128}$/.test(id)) throw new Error('Invalid SPEED resource ID.');
	return id;
}

export const taskPath = (id: string) => `agent/tasks/${routeId(id)}`;

export function startTask(objective: string, options: TaskOptions, token: string) {
	// Never automatically retry a POST: a lost response may already have created a task.
	return request<{ task_id: string }>('agent/tasks', token, {
		method: 'POST', body: JSON.stringify({ objective, flow: options.flow, input_path: options.input_path }), signal: AbortSignal.timeout(30000)
	});
}

export async function downloadArtifact(taskId: string, artifact: Artifact, token: string) {
	// Construct the route from IDs; never follow URLs or paths stored in a message.
	const response = await fetch(`/api/v1/${taskPath(taskId)}/artifacts/${routeId(artifact.id)}`, {
		headers: speedAuthHeaders(token), cache: 'no-store'
	});
	await checkResponse(response, token);
	const url = URL.createObjectURL(await response.blob());
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = artifact.name.replace(/[\\/\x00-\x1f]/g, '_');
	anchor.click();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

interface Observer {
	snapshot: (snapshot: Snapshot) => void;
	events: (events: ExecutionEvent[], truncated: boolean) => void;
	connection: (state: string) => void;
	error: (message: string) => void;
}

/** One mounted message owns one subscription. Unmount closes it; remount replays. */
export function watchTask(taskId: string, token: string, observer: Observer): () => void {
	let stopped = false;
	let socket: WebSocket | undefined;
	let retry: ReturnType<typeof setTimeout> | undefined;
	let watchdog: ReturnType<typeof setTimeout> | undefined;
	let sequence = 0;
	let attempts = 0;
	let snapshotSequence = -1;
	const abort = new AbortController();
	const stop = () => {
		stopped = true;
		abort.abort();
		clearTimeout(retry);
		clearTimeout(watchdog);
		socket?.close();
	};
	const acceptSnapshot = (snapshot: Snapshot) => {
		if (snapshot.task_id !== taskId) throw new Error('Task identity mismatch.');
		if (snapshot.last_sequence < snapshotSequence) return;
		snapshotSequence = snapshot.last_sequence;
		observer.snapshot(snapshot);
		if (terminal(snapshot.status) && snapshot.review?.status !== 'pending' && snapshot.last_sequence <= sequence) {
			observer.connection('Finished');
			stop();
		}
	};
	const receiveEvents = (events: ExecutionEvent[], truncated = false) => {
		const ordered = events.filter(e => e.task_id === taskId && e.sequence > sequence)
			.sort((a, b) => a.sequence - b.sequence);
		const unique = ordered.filter((event, index) => index === 0 || event.sequence !== ordered[index - 1].sequence);
		if (unique.length) sequence = unique[unique.length - 1].sequence;
		observer.events(unique, truncated);
	};
	const refresh = async () => {
		const snapshot = await request<Snapshot>(taskPath(taskId), token, {
			signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)])
		});
		if (!stopped) acceptSnapshot(snapshot);
	};
	const schedule = () => {
		if (stopped || retry) return;
		if (++attempts > 6) {
			observer.connection('Disconnected');
			observer.error('Connection lost. Reconnect to resume the trace; the task may still be running.');
			stop();
			return;
		}
		observer.connection('Reconnecting');
		retry = setTimeout(() => { retry = undefined; void connect(); }, Math.min(1000 * 2 ** (attempts - 1), 15000));
	};
	const fail = (error: unknown) => {
		if (stopped) return;
		if (error instanceof SpeedError && [401, 403, 404].includes(error.status)) {
			observer.connection('Unavailable');
			observer.error(error.message);
			stop();
		} else {
			socket?.close();
			schedule();
		}
	};
	async function connect() {
		try {
			observer.connection('Connecting');
			const { ticket } = await request<{ ticket: string }>(`${taskPath(taskId)}/ticket`, token,
				{ method: 'POST', signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) });
			if (stopped) return;
			const url = new URL(`/api/v1/${taskPath(taskId)}/events`, window.location.origin);
			url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			const ws = new WebSocket(url);
			socket = ws;
			const keepAlive = () => {
				clearTimeout(watchdog);
				watchdog = setTimeout(() => ws.close(), 45000);
			};
			keepAlive();
			ws.onopen = () => {
				if (stopped) return ws.close();
				ws.send(JSON.stringify({ ticket, after_sequence: sequence }));
			};
			ws.onmessage = ({ data }) => {
				if (stopped || socket !== ws) return;
				try {
					const frame = JSON.parse(data);
					keepAlive();
					if (frame.type === 'snapshot') {
						receiveEvents(frame.events, frame.history_truncated);
						sequence = Math.max(sequence, frame.snapshot.last_sequence);
						attempts = 0;
						observer.connection('Live');
						acceptSnapshot(frame.snapshot);
					} else if (frame.type === 'event') {
						const event: ExecutionEvent = frame.event;
						if (event.task_id !== taskId) return;
						if (event.sequence > sequence + 1) { ws.close(); return; }
						receiveEvents([event]);
						if (event.event_type.startsWith('plan.') || event.event_type.startsWith('task.') || event.event_type.startsWith('review.') || event.event_type === 'artifact.created') {
							void refresh().catch(fail);
						}
					}
				} catch {
					observer.error('Invalid execution stream. Reconnect to restore the task.');
					stop();
				}
			};
			ws.onerror = () => ws.close();
			ws.onclose = () => {
				if (socket !== ws) return;
				clearTimeout(watchdog);
				schedule();
			};
		} catch (error) { fail(error); }
	}
	void connect();
	return stop;
}
