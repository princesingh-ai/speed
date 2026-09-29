<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { downloadArtifact, request, taskPath, watchTask } from '$lib/speed/api';
	import { speedSession } from '$lib/speed/session.svelte';
	import { saveTaskMessage } from '$lib/speed/messages';
	import { activityRows, graphEdges, mergeEvents } from '$lib/speed/trace';
	import { belongsToMessage, terminal, type Artifact, type ExecutionEvent, type ReviewDecision, type Snapshot } from '$lib/speed/types';
	import type { DatabaseMessage } from '$lib/types';

	let { message, children, class: className = 'mx-auto w-full max-w-3xl' }: { message: DatabaseMessage; children: Snippet; class?: string } = $props();
	let events = $state<ExecutionEvent[]>([]);
	let snapshot = $state<Snapshot>();
	let connection = $state('Connecting');
	let error = $state('');
	let displayError = $derived(error || message.speedTask?.error || '');
	let truncated = $state(false);
	let manualOpen = $state<boolean | null>(null);
	let retry = $state(0);
	let pending = $state('');
	let comment = $state('');
	let now = $state(Date.now());
	let updateSnapshot: ((value: Snapshot) => Promise<void>) | undefined;
	let rows = $derived(activityRows(snapshot, events));
	let edges = $derived(graphEdges(rows));
	let width = $derived(Math.max(30, ...rows.map(r => 26 + r.lane * 16)));
	let open = $derived(manualOpen ?? snapshot?.status !== 'completed');
	let authorized = $derived(!!speedSession.token && !!message.speedTask
		&& belongsToMessage(message.speedTask, message) && speedSession.ownerId === message.speedTask.ownerId);
	let durations = $derived(events.filter(e => !e.event_type.startsWith('review.')).map(e => Date.parse(e.timestamp)).filter(Number.isFinite));
	let elapsed = $derived(durations.length > 1 ? ((durations[durations.length - 1] - durations[0]) / 1000).toFixed(1) : null);
	let status = $derived(snapshot?.status ?? (message.speedTask?.error ? 'failed' : 'starting'));
	let actions = $derived(rows.filter(r => r.status === 'completed' && r.id !== 'planning').length);
	let reviewLabel = $derived(snapshot?.review?.status === 'approved' ? 'Approved' : snapshot?.review?.status === 'changes_requested' ? 'Changes requested' : snapshot?.review?.status === 'rejected' ? 'Rejected' : 'Review required');
	let subscriptionKey = $derived(`${message.id}:${message.convId}:${message.parent}:${message.speedTask?.conversationId}:${message.speedTask?.userMessageId}:${message.speedTask?.taskId}:${message.speedTask?.ownerId}`);

	$effect(() => {
		if (terminal(status)) return;
		const clock = setInterval(() => now = Date.now(), 1000);
		return () => clearInterval(clock);
	});

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
			manualOpen = null;
			comment = '';
			updateSnapshot = undefined;
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
			const acceptSnapshot = (value: Snapshot) => {
				if (disposed || value.task_id !== taskId || (snapshot && value.last_sequence < snapshot.last_sequence)) return saving;
				snapshot = value;
				const captured = { ...link, snapshot: value, error: undefined };
				saving = saving.then(async () => {
					if (disposed) return;
					await saveTaskMessage(boundMessage, captured, terminal(value.status)
						? value.final_response || value.summary : undefined);
				}).catch(() => { if (!disposed) error = 'Unable to save task state in this browser.'; });
				return saving;
			};
			updateSnapshot = acceptSnapshot;
			const stop = watchTask(taskId, token, {
				connection: value => { connection = value; },
				error: value => { error = value; },
				events: (incoming, gap) => {
					events = mergeEvents(taskId, events, incoming);
					truncated ||= gap;
				},
				snapshot: acceptSnapshot
			});
			return () => { disposed = true; stop(); };
		});
	});

	async function review(decision: ReviewDecision) {
		const taskId = message.speedTask?.taskId;
		const accept = updateSnapshot;
		if (!taskId || !authorized || pending || snapshot?.review?.status !== 'pending' || !accept) return;
		pending = 'review';
		error = '';
		try {
			const value = await request<Snapshot>(`${taskPath(taskId)}/review`, speedSession.token, {
				method: 'POST', body: JSON.stringify({ decision, comment })
			});
			await accept(value);
		} catch (e) { error = e instanceof Error ? e.message : 'Unable to record review.'; }
		finally { pending = ''; }
	}

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

<div class={className} data-speed-column>
<section class="my-3 min-w-0 rounded-lg border border-border/60 text-sm" aria-label="SPEED agent activity">
	<button type="button" class="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left focus-visible:outline-2" aria-expanded={open} onclick={() => manualOpen = !open}>
		<span>{status === 'completed' ? `Completed ${actions} actions` : status === 'failed' ? 'Agent stopped' : 'Agent activity'}{elapsed ? ` · ${elapsed}s` : ''}</span>
		<span class="text-xs text-muted-foreground">{status}{!terminal(status) ? ` · ${rows.filter(r => r.id !== 'planning').length} actions` : ''} {open ? '-' : '+'}</span>
	</button>
	{#if snapshot?.has_mock || events.some(e => e.is_mock)}
		<p class="px-3 pb-2 text-xs text-amber-700 dark:text-amber-400">Historical simulated run. Start a new task for a real result.</p>
	{/if}
	{#if displayError}<p class="px-3 pb-2 text-xs text-destructive" role="alert">{displayError}</p>{/if}
	{#if open}
		<p class="px-3 pb-2 text-xs text-muted-foreground" role="status">{connection}</p>
		{#if truncated}<p class="px-3 pb-2 text-xs text-muted-foreground">Earlier events expired. Step states were restored from the task snapshot.</p>{/if}
		{#if !rows.length && !displayError}<p class="px-3 pb-4 text-muted-foreground">{message.speedTask?.taskId ? 'Restoring execution activity...' : 'Creating task...'}</p>{/if}
		<div class="overflow-x-auto px-3 pb-2">
			<div class="flex" style:min-width={`${width + 200}px`}>
				<svg width={width} height={rows.length * 48} class="shrink-0 text-muted-foreground" aria-hidden="true">
					{#each edges as path}<path d={path} fill="none" stroke="currentColor" stroke-opacity="0.4" stroke-width="1.5" />{/each}
					{#each rows as row, index}
						<circle cx={10 + row.lane * 16} cy={index * 48 + 20} r="4" fill="currentColor" class:running={row.status === 'running'} class:text-destructive={row.status === 'failed' || row.status === 'blocked'} class:text-amber-600={row.status === 'waiting'} class:text-emerald-600={row.status === 'completed'} />
					{/each}
				</svg>
				<ol class="min-w-0 flex-1">
					{#each rows as row (row.id)}
						<li class="activity-row h-[48px] min-w-0 py-1 pl-2" aria-current={row.status === 'running' ? 'step' : undefined}>
							<div class="truncate" title={row.title}>{row.title}</div>
							<div class="truncate text-xs text-muted-foreground" title={row.details.join(' · ')}>{row.status}{row.duration !== undefined ? ` · ${row.duration}ms` : row.status === 'running' && Number.isFinite(row.startedAt) ? ` · ${Math.max(0, Math.floor((now - row.startedAt!) / 1000))}s` : ''}{row.details.length ? ` · ${row.details.join(' · ')}` : ''}</div>
						</li>
					{/each}
				</ol>
			</div>
		</div>
		{#each rows.filter(r => r.status === 'waiting' && r.consentId && !terminal(status)) as row (row.id)}
			<div class="mx-3 mb-2 flex flex-wrap items-center gap-2 text-xs" aria-label="Tool permission">
				<span class="min-w-0 flex-1 break-words">{row.title}: {row.permission ?? 'Permission required'}{row.resource ? ` (${row.resource})` : ''}</span>
				<Button variant="outline" size="sm" disabled={!authorized || !!pending} onclick={() => consent(row.consentId!, 'approve')}>Allow tool</Button>
				<Button variant="outline" size="sm" disabled={!authorized || !!pending} onclick={() => consent(row.consentId!, 'deny')}>Deny tool</Button>
			</div>
		{/each}
	{/if}
	{#if message.speedTask?.taskId && authorized && (displayError || !terminal(status))}
		<Button variant="link" size="sm" class="mx-3 mb-3 text-xs" onclick={() => retry++}>Reconnect</Button>
	{/if}
</section>

{@render children()}

{#if snapshot?.review && status === 'completed'}
	<section class="my-3 border-t border-border/60 pt-3 text-sm" aria-label="Result review">
		<p class="font-medium" role="status">{reviewLabel}{snapshot.review.reviewer_name ? ` by ${snapshot.review.reviewer_name}` : ''}</p>
		{#if snapshot.review.status === 'pending'}
			<p class="mt-1 text-xs text-muted-foreground">Review the recommendation and document before accepting the result.</p>
			<label class="mt-2 grid gap-1 text-xs text-muted-foreground">Review note (optional)
				<textarea class="min-h-16 w-full resize-y rounded border bg-background px-2 py-1.5 text-foreground" rows="2" maxlength="2000" bind:value={comment} disabled={!authorized || !!pending}></textarea>
			</label>
			<div class="mt-2 flex flex-wrap gap-2">
				<Button size="sm" disabled={!authorized || !!pending} onclick={() => review('approved')}>Approve</Button>
				<Button variant="outline" size="sm" disabled={!authorized || !!pending} onclick={() => review('changes_requested')}>Request changes</Button>
				<Button variant="outline" size="sm" disabled={!authorized || !!pending} onclick={() => review('rejected')}>Reject</Button>
			</div>
		{:else}
			{#if snapshot.review.comment}<p class="mt-1 whitespace-pre-wrap break-words text-xs text-muted-foreground">{snapshot.review.comment}</p>{/if}
			{#if snapshot.review.reviewed_at}<time class="text-xs text-muted-foreground" datetime={snapshot.review.reviewed_at}>{new Date(snapshot.review.reviewed_at).toLocaleString()}</time>{/if}
		{/if}
	</section>
{/if}

{#if terminal(status) && message.content && snapshot?.artifacts.length}
	<div class="my-3 grid gap-2" aria-label="Generated artifacts">
		{#each snapshot.artifacts as artifact (artifact.id)}
			<div class="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
				<div class="min-w-0"><div class="truncate font-medium">{artifact.name}</div><div class="text-xs text-muted-foreground">Word document · {(artifact.size / 1024).toFixed(1)} KB</div>{#if snapshot.review}<div class="text-xs text-muted-foreground">{reviewLabel}</div>{/if}</div>
				<Button variant="outline" size="sm" class="text-xs" disabled={!authorized || !!pending} onclick={() => download(artifact)}>Download</Button>
			</div>
		{/each}
	</div>
{/if}
</div>

<style>
	.activity-row { animation: arrive 180ms ease-out; }
	.running { animation: working 1.4s ease-in-out infinite; }
	@keyframes arrive { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
	@keyframes working { 50% { opacity: 0.35; } }
	@media (prefers-reduced-motion: reduce) { .activity-row, .running { animation: none; } }
</style>
