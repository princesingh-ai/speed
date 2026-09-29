<script lang="ts">
	import { LoaderCircle, Shield } from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { ROUTES } from '$lib/constants';
	import { authStore } from '$lib/stores';

	let username = $state('');
	let password = $state('');
	let isSubmitting = $state(false);
	let localError = $state('');

	const canSubmit = $derived(username.trim().length > 0 && password.trim().length > 0);

	async function handleSubmit() {
		if (!canSubmit || isSubmitting) return;

		isSubmitting = true;
		localError = '';

		try {
			await authStore.login(username.trim(), password);
			await goto(ROUTES.START, { replaceState: true });
		} catch {
			localError = authStore.error ?? 'Invalid username or password.';
		} finally {
			isSubmitting = false;
		}
	}
</script>

<main class="flex min-h-dvh items-center justify-center bg-background px-4 py-8 text-foreground">
	<Card.Root class="w-full max-w-sm gap-5 rounded-2xl border-border/50 bg-card/80 px-6 py-6 shadow-sm">
		<Card.Header class="px-0">
			<div class="mb-3 flex items-center gap-3">
				<div class="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-foreground">
					<Shield class="h-4 w-4" aria-hidden="true" />
				</div>

				<p class="text-sm font-semibold tracking-widest">SPEED</p>
				{#if authStore.demoMode}<span class="text-xs text-muted-foreground">Demo</span>{/if}
			</div>

			<Card.Title class="text-xl">Sign in to SPEED</Card.Title>
			<Card.Description>Secure local AI workbench</Card.Description>
		</Card.Header>

		<Card.Content class="px-0">
			<form class="space-y-4" onsubmit={(event) => {
				event.preventDefault();
				void handleSubmit();
			}}>
				<div class="space-y-2">
					<Label for="speed-username">Username</Label>
					<Input
						aria-invalid={Boolean(localError)}
						autocomplete="username"
						bind:value={username}
						disabled={isSubmitting}
						id="speed-username"
						required
						type="text"
					/>
				</div>

				<div class="space-y-2">
					<Label for="speed-password">Password</Label>
					<Input
						aria-invalid={Boolean(localError)}
						autocomplete="current-password"
						bind:value={password}
						disabled={isSubmitting}
						id="speed-password"
						required
						type="password"
					/>
				</div>

				{#if localError}
					<Alert role="alert" class="py-2" variant="destructive">
						<AlertDescription>{localError}</AlertDescription>
					</Alert>
				{/if}

				<Button class="w-full" disabled={!canSubmit || isSubmitting} type="submit">
					{#if isSubmitting}
						<LoaderCircle class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
					{/if}

					Sign in
				</Button>
			</form>
		</Card.Content>
	</Card.Root>
</main>
