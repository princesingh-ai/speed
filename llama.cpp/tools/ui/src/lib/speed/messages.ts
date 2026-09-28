import { DatabaseService } from '$lib/services/database.service';
import { conversationsStore } from '$lib/stores/conversations/index.svelte';
import type { DatabaseMessage } from '$lib/types';
import type { TaskLink } from './types';
import { belongsToMessage } from './types';

export async function saveTaskMessage(message: DatabaseMessage, link: TaskLink, content?: string) {
	if (!belongsToMessage(link, message)) return;
	if (link.snapshot && link.snapshot.task_id !== link.taskId) return;
	const updates = { speedTask: link, ...(content === undefined ? {} : { content }) };
	// Retain a usable live task handle even if IndexedDB is full/unavailable.
	if (conversationsStore.activeConversation?.id === message.convId) {
		conversationsStore.updateMessageAtIndex(conversationsStore.findMessageIndex(message.id), updates);
	}
	// update() never recreates a deleted message. Do not append into an active conversation.
	await DatabaseService.updateMessage(message.id, updates);
}
