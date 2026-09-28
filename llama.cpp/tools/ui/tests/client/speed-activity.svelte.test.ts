import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import Harness from './SpeedActivityHarness.svelte';
import { speedSession } from '../../src/lib/speed/session.svelte';
import type { watchTask } from '../../src/lib/speed/api';
import type { DatabaseMessage } from '../../src/lib/types/database';
import { event, snapshot } from '../unit/speed-fixtures';

type Observer = Parameters<typeof watchTask>[2];
const mocks = vi.hoisted(() => ({ observer: undefined as Observer | undefined, stop: vi.fn(), request: vi.fn(async () => ({})),
	download: vi.fn(async () => {}), save: vi.fn(async () => {}) }));
vi.mock('$lib/speed/api', () => ({
	watchTask: (_id: string, _token: string, observer: Observer) => { mocks.observer = observer; return mocks.stop; },
	request: mocks.request, downloadArtifact: mocks.download
}));
vi.mock('$lib/speed/messages', () => ({ saveTaskMessage: mocks.save }));

let target: HTMLDivElement;
let app: ReturnType<typeof mount> | undefined;
const message = (status = 'running', content = '') => ({
	id: 'assistant', convId: 'conversation', parent: 'user', role: 'assistant', type: 'text',
	content, children: [], timestamp: 1, speedTask: {
		conversationId: 'conversation', userMessageId: 'user', ownerId: 'owner', taskId: 'task-a',
		snapshot: snapshot([{ id: 'read', title: 'Read report', status }], { status })
	}
}) as DatabaseMessage;

beforeEach(() => {
	vi.clearAllMocks();
	mocks.observer = undefined;
	speedSession.token = 'test-token';
	speedSession.ownerId = 'owner';
	target = document.createElement('div');
	document.body.append(target);
});
afterEach(async () => { if (app) await unmount(app); app = undefined; target.remove(); speedSession.logout(); });

async function show(value: DatabaseMessage) {
	app = mount(Harness, { target, props: { message: value } });
	await tick();
}
const disclosure = () => target.querySelector<HTMLButtonElement>('button[aria-expanded]')!;

it('shows inline activity immediately, expands running work and closes its observer on unmount', async () => {
	await show(message());
	expect(target.querySelector('[aria-label="SPEED agent activity"]')).not.toBeNull();
	expect(disclosure().getAttribute('aria-expanded')).toBe('true');
	expect(target.querySelector('[data-final-response]')).toBeNull();
	await unmount(app!); app = undefined;
	expect(mocks.stop).toHaveBeenCalledOnce();
});

it('collapses completion but respects a manual expansion through snapshot updates', async () => {
	await show(message('completed', 'Real response'));
	expect(disclosure().getAttribute('aria-expanded')).toBe('false');
	expect(disclosure().textContent).toContain('Completed 1 actions');
	disclosure().click();
	await tick();
	mocks.observer?.snapshot(snapshot([{ id: 'read', status: 'completed' }], { status: 'completed', last_sequence: 5, final_response: 'Real response' }));
	await tick();
	expect(disclosure().getAttribute('aria-expanded')).toBe('true');
	expect(target.querySelector('[data-final-response]')?.textContent).toBe('Real response');
});

it('auto-collapses on completion and keeps failed runs open', async () => {
	await show(message());
	mocks.observer?.snapshot(snapshot([{ id: 'read', status: 'completed' }], { status: 'completed', last_sequence: 2 }));
	await tick();
	expect(disclosure().getAttribute('aria-expanded')).toBe('false');
	await unmount(app!); app = undefined;
	await show(message('failed'));
	expect(disclosure().getAttribute('aria-expanded')).toBe('true');
	expect(target.textContent).toContain('Agent stopped');
});

it('renders mock, waiting and explicit consent without auto-approving', async () => {
	await show(message());
	mocks.observer?.events([event(1, { event_type: 'step.waiting', status: 'waiting', is_mock: true,
		metadata: { consent_id: 'consent-1', permission: 'sandbox.execute' } })], false);
	await tick();
	expect(target.textContent).toContain('Includes mock content');
	expect(target.textContent).toContain('waiting');
	expect(mocks.request).not.toHaveBeenCalled();
	const reject = [...target.querySelectorAll('button')].find(button => button.textContent === 'Reject')!;
	reject.click();
	await tick();
	expect(mocks.request).toHaveBeenCalledWith('permissions/consent-1/deny', 'test-token', { method: 'POST' });
});

it('places registered artifacts after final prose and downloads with task ownership context', async () => {
	const value = message('completed', 'Actual model output');
	const artifact = { id: 'word', name: 'approval-note.docx', size: 1234, is_mock: false };
	value.speedTask!.snapshot!.artifacts = [artifact];
	await show(value);
	const prose = target.querySelector('[data-final-response]')!;
	const artifacts = target.querySelector('[aria-label="Generated artifacts"]')!;
	expect(prose.compareDocumentPosition(artifacts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	[...artifacts.querySelectorAll('button')][0].click();
	await tick();
	expect(mocks.download).toHaveBeenCalledWith('task-a', artifact, 'test-token');
});

it('does not subscribe copied task associations or a different signed-in owner', async () => {
	const copied = message(); copied.convId = 'other-conversation';
	await show(copied);
	expect(mocks.observer).toBeUndefined();
	expect(target.textContent).toContain('does not belong');
	await unmount(app!); app = undefined;
	speedSession.ownerId = 'other-owner';
	await show(message());
	expect(mocks.observer).toBeUndefined();
	expect(target.textContent).toContain('Connect as the task owner');
});
