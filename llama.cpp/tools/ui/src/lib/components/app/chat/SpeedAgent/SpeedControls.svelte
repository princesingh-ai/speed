<script lang="ts">
	import { speedSession } from '$lib/speed/session.svelte';
	import { Button } from '$lib/components/ui/button';
	let username = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);
	async function login() {
		busy = true;
		error = '';
		try { await speedSession.login(username, password); }
		catch (e) { error = e instanceof Error ? e.message : 'Unable to connect.'; }
		finally { password = ''; busy = false; }
	}
</script>

<div class="mx-auto mb-2 flex max-w-3xl flex-wrap items-center gap-3 px-3 text-xs text-muted-foreground">
	<label class="flex items-center gap-2">
		<input type="checkbox" bind:checked={speedSession.enabled} /> SPEED agent
	</label>
	{#if speedSession.enabled}
		<span title="SPEED executes against the server workspace; this is not an air-gap guarantee.">Local agent · Auto routing</span>
		<details class="min-w-0">
			<summary class="cursor-pointer">{speedSession.token ? 'Agent settings' : 'Connect to SPEED'}</summary>
			<div class="my-3 grid gap-3 rounded-lg border bg-background p-3 text-foreground">
				{#if speedSession.token}
					<div>Connected as {speedSession.username} <Button variant="link" size="sm" onclick={() => speedSession.logout()}>Disconnect</Button></div>
				{:else}
					<p>SPEED uses a separate sign-in from chat. Sign in again after refreshing.</p>
					<label>Username <input class="ml-2 rounded border bg-transparent p-1" autocomplete="username" bind:value={username} /></label>
					<label>Password <input class="ml-2 rounded border bg-transparent p-1" type="password" autocomplete="current-password" bind:value={password} /></label>
					<Button variant="outline" size="sm" disabled={busy || !username || !password} onclick={login}>{busy ? 'Connecting...' : 'Connect'}</Button>
				{/if}
				<label>Workflow <select class="ml-2 rounded border bg-background p-1" bind:value={speedSession.options.flow}>
					<option value="document">Document</option><option value="mcp">Document + local MCP</option><option value="coding">Coding sandbox</option>
				</select></label>
				<label>Workspace report <input class="ml-2 max-w-full rounded border bg-transparent p-1" bind:value={speedSession.options.input_path} /></label>
				<label class="flex items-center gap-2"><input type="checkbox" bind:checked={speedSession.options.demo_mode} /> Demonstration analysis (mock)</label>
				<p>Uses the server workspace. Uploads and chat history are not sent to the agent. Sandbox and MCP may require approval.</p>
				{#if error}<p role="alert">{error}</p>{/if}
			</div>
		</details>
	{/if}
</div>
