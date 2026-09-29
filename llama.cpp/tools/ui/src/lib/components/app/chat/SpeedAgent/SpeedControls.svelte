<script lang="ts">
	import { speedSession } from '$lib/speed/session.svelte';
	let settingsOpen = $state(true);
	const workflows = { document: 'Document', mcp: 'Document + MCP', coding: 'Coding' };
</script>

<div class="pointer-events-auto mx-auto mb-2 w-full max-w-3xl px-3 text-xs text-muted-foreground">
	<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
	<label class="flex cursor-pointer items-center gap-2 font-medium text-foreground">
		<input type="checkbox" bind:checked={speedSession.enabled} onchange={() => settingsOpen = true} /> SPEED Agent
	</label>
	{#if speedSession.enabled}
		<span>{workflows[speedSession.options.flow]} · Auto routing</span>
		<button type="button" class="ml-auto rounded px-2 py-1 hover:text-foreground focus-visible:outline-2" aria-expanded={settingsOpen} aria-controls="speed-agent-settings" onclick={() => settingsOpen = !settingsOpen}>Settings {settingsOpen ? '-' : '+'}</button>
	{/if}
	</div>
	{#if speedSession.enabled && settingsOpen}
		<div id="speed-agent-settings" class="mt-2 grid gap-2 border-t border-border/60 pt-2 sm:grid-cols-2">
				<label class="grid gap-1">Workflow <select class="min-w-0 rounded border bg-background px-2 py-1.5 text-foreground" bind:value={speedSession.options.flow}>
					<option value="document">Document</option><option value="mcp">Document + local MCP</option><option value="coding">Coding sandbox</option>
				</select></label>
				<label class="grid gap-1">Workspace input <input class="min-w-0 rounded border bg-background px-2 py-1.5 text-foreground" maxlength="500" bind:value={speedSession.options.input_path} /></label>
				<p class="sm:col-span-2">Uses the local server workspace. Tools may request approval. Chat attachments are not included.</p>
		</div>
	{/if}
</div>
