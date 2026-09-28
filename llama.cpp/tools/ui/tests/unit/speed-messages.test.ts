import { beforeEach, expect, it, vi } from 'vitest';
import type { DatabaseMessage } from '../../src/lib/types/database';

const mocks = vi.hoisted(() => ({
	update: vi.fn(async () => {}),
	store: { activeConversation: { id: 'conv-a' }, findMessageIndex: vi.fn(() => 2), updateMessageAtIndex: vi.fn() }
}));
vi.mock('$lib/services/database.service', () => ({ DatabaseService: { updateMessage: mocks.update } }));
vi.mock('$lib/stores/conversations/index.svelte', () => ({ conversationsStore: mocks.store }));
import { saveTaskMessage } from '../../src/lib/speed/messages';
import { snapshot } from './speed-fixtures';

const message = { id: 'assistant-a', convId: 'conv-a', parent: 'user-a' } as DatabaseMessage;
const link = { conversationId: 'conv-a', userMessageId: 'user-a', taskId: 'task-a', ownerId: 'owner' };

beforeEach(() => { vi.clearAllMocks(); mocks.update.mockResolvedValue(undefined); mocks.store.activeConversation = { id: 'conv-a' }; });

it('persists task identity on the same assistant message', async () => {
	await saveTaskMessage(message, link, 'Actual model output');
	expect(mocks.update).toHaveBeenCalledWith('assistant-a', { speedTask: link, content: 'Actual model output' });
	expect(mocks.store.updateMessageAtIndex).toHaveBeenCalledWith(2, { speedTask: link, content: 'Actual model output' });
});

it('updates persisted task A without appending or mutating active conversation B', async () => {
	mocks.store.activeConversation = { id: 'conv-b' };
	await saveTaskMessage(message, link, 'A result');
	expect(mocks.update).toHaveBeenCalledOnce();
	expect(mocks.store.updateMessageAtIndex).not.toHaveBeenCalled();
});

it('rejects a link copied under another turn or conversation', async () => {
	await saveTaskMessage(message, { ...link, conversationId: 'conv-b' });
	await saveTaskMessage(message, { ...link, userMessageId: 'other-user-turn' });
	await saveTaskMessage(message, { ...link, snapshot: snapshot([], { task_id: 'task-b' }) });
	expect(mocks.update).not.toHaveBeenCalled();
});

it('keeps the live task handle visible if browser persistence fails', async () => {
	mocks.update.mockRejectedValueOnce(new Error('Quota exceeded'));
	await expect(saveTaskMessage(message, link)).rejects.toThrow('Quota exceeded');
	expect(mocks.store.updateMessageAtIndex).toHaveBeenCalledWith(2, { speedTask: link });
});
