import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import '../../src/app.css';
import Harness from './SpeedActivityHarness.svelte';
import { speedSession } from '../../src/lib/speed/session.svelte';
import type { watchTask } from '../../src/lib/speed/api';
import type { DatabaseMessage } from '../../src/lib/types/database';
import type { ReviewDecision, TaskLink } from '../../src/lib/speed/types';
import { event, snapshot } from '../unit/speed-fixtures';

type Observer = Parameters<typeof watchTask>[2];
const mocks = vi.hoisted(() => ({ observer: undefined as Observer | undefined, stop: vi.fn(), request: vi.fn(async () => ({})),
	download: vi.fn(async () => {}), save: vi.fn(async (_message: DatabaseMessage, _link: TaskLink, _content?: string) => {}) }));
vi.mock('$lib/speed/api', () => ({
	watchTask: (_id: string, _token: string, observer: Observer) => { mocks.observer = observer; return mocks.stop; },
	request: mocks.request, downloadArtifact: mocks.download, taskPath: (id: string) => `agent/tasks/${id}`
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

it('keeps legacy simulation disclosure and tool permission separate from result review', async () => {
	await show(message());
	mocks.observer?.events([event(1, { event_type: 'step.waiting', status: 'waiting', is_mock: true,
		metadata: { consent_id: 'consent-1', permission: 'sandbox.execute' } })], false);
	await tick();
	expect(target.textContent).toContain('Historical simulated run');
	expect(target.textContent).not.toMatch(/mock/i);
	expect(target.textContent).toContain('waiting');
	expect(mocks.request).not.toHaveBeenCalled();
	const reject = [...target.querySelectorAll('button')].find(button => button.textContent === 'Deny tool')!;
	reject.click();
	await tick();
	expect(mocks.request).toHaveBeenCalledWith('permissions/consent-1/deny', 'test-token', { method: 'POST' });
});

it('uses the centered chat width and immediately renders incoming running steps', async () => {
	target.style.width = '1200px';
	await show(message());
	const column = target.querySelector<HTMLElement>('[data-speed-column]')!;
	expect(column.classList.contains('max-w-3xl')).toBe(true);
	expect(column.getBoundingClientRect().width).toBeLessThan(target.getBoundingClientRect().width);
	mocks.observer?.events([event(1, { event_type: 'step.started', status: 'running' })], false);
	await tick();
	expect(target.querySelector('[aria-current="step"]')).not.toBeNull();
	expect(target.querySelector('svg circle.running')).not.toBeNull();
	expect(target.textContent).not.toMatch(/MOCK|Mock content/);
});

it.each([
	['Approve', 'approved'], ['Request changes', 'changes_requested'], ['Reject', 'rejected']
])('records %s and restores its decision when reopening', async (label, decision) => {
	const value = message('completed', 'Recommendation: conditional approval.');
	const review = { status: 'pending' as const, comment: '', reviewed_by: null, reviewer_name: null, reviewed_at: null };
	value.speedTask!.snapshot!.review = review;
	const updated = { ...value.speedTask!.snapshot!, last_sequence: 5,
		review: { ...review, status: decision as ReviewDecision, comment: 'Check the seal.', reviewed_by: 'owner', reviewer_name: 'admin', reviewed_at: '2026-01-01T00:01:00Z' } };
	mocks.request.mockResolvedValueOnce(updated);
	await show(value);
	const card = target.querySelector('[aria-label="Result review"]')!;
	expect(card.textContent).toContain('Review required');
	const note = card.querySelector('textarea')!;
	note.value = 'Check the seal.';
	note.dispatchEvent(new Event('input', { bubbles: true }));
	await tick();
	[...card.querySelectorAll('button')].find(button => button.textContent?.trim() === label)!.click();
	await vi.waitFor(() => expect(mocks.save).toHaveBeenCalled());
	await tick();
	expect(mocks.request).toHaveBeenCalledWith('agent/tasks/task-a/review', 'test-token', {
		method: 'POST', body: JSON.stringify({ decision, comment: 'Check the seal.' })
	});
	expect(card.querySelector('textarea')).toBeNull();
	expect(card.textContent).toContain('by admin');
	const saved = mocks.save.mock.calls[0][1];
	expect(saved.snapshot?.review?.status).toBe(decision);
	await unmount(app!); app = undefined;
	await show({ ...value, speedTask: saved });
	expect(target.querySelector('[aria-label="Result review"]')!.textContent).toContain('Check the seal.');
	expect(target.querySelector('[aria-label="Result review"] textarea')).toBeNull();
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
