import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import type { DatabaseMessage } from '../../src/lib/types/database';
import { MessageRole, MessageType, ServerModelStatus } from '../../src/lib/enums';

const mocks = vi.hoisted(() => ({
	create: vi.fn(), start: vi.fn(), save: vi.fn(), load: vi.fn(),
	modelStatus: vi.fn(),
	conversations: {
		activeConversation: { id: 'conv', currNode: 'previous' }, activeMessages: [],
		addMessageToActive: vi.fn(), updateConversationTimestamp: vi.fn()
	}
}));
vi.mock('$lib/services/database.service', () => ({ DatabaseService: { createMessageBranch: mocks.create } }));
vi.mock('$lib/services/chat.service', () => ({ ChatService: {} }));
vi.mock('$lib/speed/api', () => ({ startTask: mocks.start }));
vi.mock('$lib/speed/messages', () => ({ saveTaskMessage: mocks.save }));
vi.mock('$lib/speed/session.svelte', () => ({ speedSession: {
	enabled: true, token: 'token', ownerId: 'owner', options: { flow: 'document', demo_mode: true, input_path: 'report.txt' }
} }));
vi.mock('$lib/stores/conversations/index.svelte', () => ({ conversationsStore: mocks.conversations }));
vi.mock('$lib/stores/agentic/index.svelte', () => ({ agenticStore: { isRunning: () => false } }));
vi.mock('$lib/stores/chat/activity.svelte', () => ({ chatActivityStore: { isLocal: () => false } }));
vi.mock('$lib/stores/chat/processing.svelte', () => ({ chatProcessingStore: {} }));
vi.mock('$lib/stores/chat/flows.svelte', () => ({ ChatMessageFlows: class {} }));
vi.mock('$lib/stores/chat/streams.svelte', () => ({ ChatStreamManager: class {} }));
vi.mock('$lib/stores/mcp/index.svelte', () => ({ mcpStore: { resources: { hasAttachments: false } } }));
vi.mock('$lib/stores/models/index.svelte', () => ({ modelsStore: {} }));
vi.mock('$lib/stores/server.svelte', () => ({ serverStore: {} }));
vi.mock('$lib/stores/settings/index.svelte', () => ({ settingsStore: {} }));
vi.mock('$lib/stores/tools.svelte', () => ({ toolsStore: {} }));
vi.mock('$lib/stores', () => ({ modelsStore: { getModelStatus: mocks.modelStatus, status: { load: mocks.load } } }));
vi.mock('$lib/utils', () => ({
	findMessageById: vi.fn(), formatCwdMessage: vi.fn(), getConversationModel: vi.fn(),
	isAbortError: vi.fn(), normalizeModelName: vi.fn(), copyToClipboard: vi.fn()
}));
vi.mock('$lib/components/app', async () => {
	const { default: Stub } = await import('./ModelControlStub.svelte');
	return { ModelBadge: Stub, ModelsSelectorDropdown: Stub };
});

import { chatStore } from '../../src/lib/stores/chat/index.svelte';
import AssistantModel from '../../src/lib/components/app/chat/ChatMessages/ChatMessage/ChatMessageAssistant/ChatMessageAssistantModel.svelte';

let app: ReturnType<typeof mount> | undefined;
let target: HTMLDivElement;
const user: DatabaseMessage = { id: 'user', convId: 'conv', parent: 'previous', role: MessageRole.USER,
	type: MessageType.TEXT, content: 'Review', children: [], timestamp: 1 };
const assistant: DatabaseMessage = { ...user, id: 'assistant', parent: 'user', role: MessageRole.ASSISTANT, content: '' };

beforeEach(() => {
	vi.resetAllMocks();
	chatStore.errorDialogState = null;
	mocks.conversations.activeConversation = { id: 'conv', currNode: 'previous' };
	mocks.start.mockResolvedValue({ task_id: 'task-a' });
	mocks.modelStatus.mockReturnValue(ServerModelStatus.LOADED);
	target = document.createElement('div');
	document.body.append(target);
});
afterEach(async () => { if (app) await unmount(app); app = undefined; target.remove(); });

it.each(['reject', 'missing', 'foreign'])('never starts a task when assistant creation is %s', async failure => {
	mocks.create.mockResolvedValueOnce(user);
	if (failure === 'reject') mocks.create.mockRejectedValueOnce(new Error('Persistence failed'));
	else mocks.create.mockResolvedValueOnce(failure === 'missing' ? undefined : { ...assistant, convId: 'other' });
	await chatStore.sendMessage('Review', undefined, true);
	expect(mocks.start).not.toHaveBeenCalled();
	expect(chatStore.errorDialogState).not.toBeNull();
	expect(chatStore.agentSubmitting).toBe(false);
});

it('creates the assistant before starting and linking a SPEED task', async () => {
	mocks.create.mockResolvedValueOnce(user).mockResolvedValueOnce({ ...assistant });
	await chatStore.sendMessage('Review', undefined, true);
	expect(mocks.create.mock.invocationCallOrder[1]).toBeLessThan(mocks.start.mock.invocationCallOrder[0]);
	expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ id: 'assistant' }), {
		conversationId: 'conv', userMessageId: 'user', ownerId: 'owner', taskId: 'task-a'
	});
});

it('renders a model badge without regeneration when no callback exists', async () => {
	app = mount(AssistantModel, { target, props: { displayedModel: 'Existing model', isRouter: true, isLoading: false } });
	await tick();
	expect(target.textContent).toContain('Existing model');
	expect(target.querySelector('button')).toBeNull();
	expect(mocks.load).not.toHaveBeenCalled();
});

it('keeps model selection and regeneration working when supplied', async () => {
	const regenerate = vi.fn();
	app = mount(AssistantModel, { target, props: { displayedModel: 'Existing model', isRouter: true, isLoading: false, onRegenerate: regenerate } });
	await tick();
	target.querySelector('button')?.click();
	await tick();
	expect(regenerate).toHaveBeenCalledWith('Model name');
});
