<script lang="ts">
	import { speedSession } from '$lib/speed/session.svelte';
</script>

<div class="pointer-events-auto mx-auto mb-2 flex max-w-3xl flex-wrap items-center gap-3 px-3 text-xs text-muted-foreground">
	<label class="flex items-center gap-2">
		<input type="checkbox" bind:checked={speedSession.enabled} /> SPEED agent
	</label>
	{#if speedSession.enabled}
		<span title="SPEED executes against the server workspace; this is not an air-gap guarantee.">Local agent · Auto routing</span>
		<details open class="min-w-0">
			<summary class="cursor-pointer">Agent settings</summary>
			<div class="my-3 grid gap-3 rounded-lg border bg-background p-3 text-foreground">
				<p>Signed in as {speedSession.username}</p>
				<label>Workflow <select class="ml-2 rounded border bg-background p-1" bind:value={speedSession.options.flow}>
					<option value="document">Document</option><option value="mcp">Document + local MCP</option><option value="coding">Coding sandbox</option>
				</select></label>
				<label>Workspace report <input class="ml-2 max-w-full rounded border bg-transparent p-1" bind:value={speedSession.options.input_path} /></label>
				<label class="flex items-center gap-2"><input type="checkbox" bind:checked={speedSession.options.demo_mode} /> Demonstration analysis (mock)</label>
				<p>Uses the server workspace. Uploads and chat history are not sent to the agent. Sandbox and MCP may require approval.</p>
			</div>
		</details>
	{/if}
</div>
