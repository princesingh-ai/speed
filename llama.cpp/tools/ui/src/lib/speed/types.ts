export interface ExecutionEvent {
	event_id: string;
	sequence: number;
	task_id: string;
	step_id: string | null;
	event_type: string;
	status: string;
	title: string;
	timestamp: string;
	duration_ms: number | null;
	metadata: Record<string, unknown>;
	is_mock: boolean;
}

export interface Step {
	id: string;
	title: string;
	kind: string;
	dependencies: string[];
	status: string;
}

export interface Artifact {
	id: string;
	name: string;
	size: number;
	is_mock: boolean;
}

export interface Snapshot {
	task_id: string;
	status: string;
	steps: Step[];
	artifacts: Artifact[];
	last_sequence: number;
	has_mock: boolean;
	summary: string;
	final_response: string;
	planner_mode: string | null;
}

export interface TaskLink {
	conversationId: string;
	userMessageId: string;
	taskId?: string;
	ownerId: string;
	error?: string;
	snapshot?: Snapshot;
}

export interface TaskOptions {
	flow: 'document' | 'mcp' | 'coding';
	demo_mode: boolean;
	input_path: string;
}

export const terminal = (status?: string) => status === 'completed' || status === 'failed';

export function belongsToMessage(link: TaskLink, message: { convId: string; parent: string | null }) {
	return link.conversationId === message.convId && link.userMessageId === message.parent;
}
