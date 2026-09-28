<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { downloadArtifact, request, watchTask } from '$lib/speed/api';
	import { speedSession } from '$lib/speed/session.svelte';
	import { saveTaskMessage } from '$lib/speed/messages';
	import { activityRows, graphEdges, mergeEvents } from '$lib/speed/trace';
	import { belongsToMessage, terminal, type Artifact, type ExecutionEvent, type Snapshot } from '$lib/speed/types';
	import type { DatabaseMessage } from '$lib/types';

	let { message, children }: { message: DatabaseMessage; children: Snippet } = $props();
	let events = $state<ExecutionEvent[]>([]);
	let snapshot = $state<Snapshot>();
	let connection = $state('Connecting');
	let error = $state('');
	let displayError = $derived(error || message.speedTask?.error || '');
	let truncated = $state(false);
	let manualOpen = $state<boolean | null>(null);
	let retry = $state(0);
	let pending = $state('');
	let rows = $derived(activityRows(snapshot, events));
	let edges = $derived(graphEdges(rows));
	let width = $derived(Math.max(30, ...rows.map(r => 26 + r.lane * 16)));
	let open = $derived(manualOpen ?? snapshot?.status !== 'completed');
	let authorized = $derived(!!speedSession.token && !!message.speedTask
		&& belongsToMessage(message.speedTask, message) && speedSession.ownerId === message.speedTask.ownerId);
	let durations = $derived(events.map(e => Date.parse(e.timestamp)).filter(Number.isFinite));
	let elapsed = $derived(durations.length > 1 ? ((durations[durations.length - 1] - durations[0]) / 1000).toFixed(1) : null);
	let status = $derived(snapshot?.status ?? (message.speedTask?.error ? 'failed' : 'starting'));
	let actions = $derived(rows.filter(r => r.status === 'completed' && r.id !== 'planning').length);
	let subscriptionKey = $derived(`${message.id}:${message.convId}:${message.parent}:${message.speedTask?.conversationId}:${message.speedTask?.userMessageId}:${message.speedTask?.taskId}:${message.speedTask?.ownerId}`);

	$effect(() => {
		void subscriptionKey;
		const token = speedSession.token;
		const ownerId = speedSession.ownerId;
		void retry;
		return untrack(() => {
			const boundMessage = message;
			const link = message.speedTask;
			const taskId = link?.taskId;
			snapshot = undefined;
			events = [];
			if (!link || !belongsToMessage(link, message)) {
				error = 'This copied task link does not belong to this conversation turn.';
				return;
			}
			snapshot = link.snapshot?.task_id === taskId ? link.snapshot : undefined;
			truncated = false;
			error = link.error ?? '';
			if (!taskId) return;
			if (!token || ownerId !== link.ownerId) {
				connection = 'Connect as the task owner to restore activity';
				return;
			}
			let disposed = false;
			// Serialize persistence so an older HTTP response cannot overwrite a terminal result.
			let saving = Promise.resolve();
			const stop = watchTask(taskId, token, {
				connection: value => { connection = value; },
				error: value => { error = value; },
				events: (incoming, gap) => {
					events = mergeEvents(taskId, events, incoming);
					truncated ||= gap;
				},
				snapshot: value => {
					if (snapshot && value.last_sequence < snapshot.last_sequence) return;
					snapshot = value;
					const captured = { ...link, snapshot: value, error: undefined };
					saving = saving.then(async () => {
						if (disposed) return;
						await saveTaskMessage(boundMessage, captured, terminal(value.status)
							? value.final_response || value.summary : undefined);
					}).catch(() => { if (!disposed) error = 'Unable to save task state in this browser.'; });
				}
			});
			return () => { disposed = true; stop(); };
		});
	});

	async function consent(id: string, decision: 'approve' | 'deny') {
		if (!authorized || pending || terminal(status)) return;
		pending = id;
		error = '';
		try {
			await request(`permissions/${encodeURIComponent(id)}/${decision}`, speedSession.token, { method: 'POST' });
		} catch (e) { error = e instanceof Error ? e.message : 'Approval request failed.'; }
		finally { pending = ''; }
	}

	async function download(artifact: Artifact) {
		const taskId = message.speedTask?.taskId;
		if (!taskId || !authorized) return;
		pending = artifact.id;
		try { await downloadArtifact(taskId, artifact, speedSession.token); }
		catch (e) { error = e instanceof Error ? e.message : 'Download failed.'; }
		finally { pending = ''; }
	}
</script>

<section class="my-4 min-w-0 rounded-lg border border-border/60 text-sm" aria-label="SPEED agent activity">
	<button type="button" class="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-3 text-left focus-visible:outline-2" aria-expanded={open} onclick={() => manualOpen = !open}>
		<span>{status === 'completed' ? `Completed ${actions} actions` : status === 'failed' ? 'Agent stopped' : 'Agent activity'}{elapsed ? ` · ${elapsed}s` : ''}</span>
		<span class="text-xs text-muted-foreground">{status} {open ? '−' : '+'}</span>
	</button>
	{#if snapshot?.has_mock || events.some(e => e.is_mock)}
		<p class="px-3 pb-2 text-xs text-amber-700 dark:text-amber-400">Includes mock content. Human review required.</p>
	{/if}
	{#if displayError}<p class="px-3 pb-2 text-xs text-destructive" role="alert">{displayError}</p>{/if}
	{#if open}
		<p class="px-3 pb-2 text-xs text-muted-foreground" role="status">{connection}</p>
		{#if truncated}<p class="px-3 pb-2 text-xs text-muted-foreground">Earlier events expired. Step states were restored from the task snapshot.</p>{/if}
		{#if !rows.length && !displayError}<p class="px-3 pb-4 text-muted-foreground">{message.speedTask?.taskId ? 'Restoring execution activity...' : 'Creating task...'}</p>{/if}
		<div class="overflow-x-auto px-3 pb-3">
			<div class="flex" style:min-width={`${width + 200}px`}>
				<svg width={width} height={rows.length * 76} class="shrink-0 text-muted-foreground" aria-hidden="true">
					{#each edges as path}<path d={path} fill="none" stroke="currentColor" stroke-opacity="0.4" stroke-width="1.5" />{/each}
					{#each rows as row, index}
						<circle cx={10 + row.lane * 16} cy={index * 76 + 20} r="4" fill="currentColor" class:text-destructive={row.status === 'failed' || row.status === 'blocked'} class:text-amber-600={row.status === 'waiting'} class:text-emerald-600={row.status === 'completed'} />
					{/each}
				</svg>
				<ol class="min-w-0 flex-1">
					{#each rows as row (row.id)}
						<li class="h-[76px] min-w-0 py-2 pl-2">
							<div class="truncate" title={row.title}>{row.title}</div>
							<div class="truncate text-xs text-muted-foreground" title={row.details.join(' · ')}>{row.status}{row.duration !== undefined ? ` · ${row.duration}ms` : ''}{row.mock ? ' · MOCK' : ''}{row.details.length ? ` · ${row.details.join(' · ')}` : ''}</div>
							{#if row.status === 'waiting' && row.consentId && !terminal(status)}
								<div class="flex items-center gap-2 text-xs">
									<span class="truncate" title={row.resource}>{row.permission ?? 'Approval required'}</span>
									<Button variant="link" size="sm" class="h-5 px-1 text-xs" disabled={!authorized || !!pending} onclick={() => consent(row.consentId!, 'approve')}>Approve</Button>
									<Button variant="link" size="sm" class="h-5 px-1 text-xs" disabled={!authorized || !!pending} onclick={() => consent(row.consentId!, 'deny')}>Reject</Button>
								</div>
							{/if}
						</li>
					{/each}
				</ol>
			</div>
		</div>
	{/if}
	{#if message.speedTask?.taskId && authorized && (displayError || !terminal(status))}
		<Button variant="link" size="sm" class="mx-3 mb-3 text-xs" onclick={() => retry++}>Reconnect</Button>
	{/if}
</section>

{@render children()}

{#if terminal(status) && message.content && snapshot?.artifacts.length}
	<div class="my-3 grid gap-2" aria-label="Generated artifacts">
		{#each snapshot.artifacts as artifact (artifact.id)}
			<div class="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
				<div class="min-w-0"><div class="truncate font-medium">{artifact.name}</div><div class="text-xs text-muted-foreground">Word document · {artifact.size} bytes{artifact.is_mock ? ' · Mock content' : ''}</div></div>
				<Button variant="outline" size="sm" class="text-xs" disabled={!authorized || !!pending} onclick={() => download(artifact)}>Download</Button>
			</div>
		{/each}
	</div>
{/if}
