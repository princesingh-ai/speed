<script lang="ts">
	import SpeedAgentActivity from '../../src/lib/components/app/chat/SpeedAgent/SpeedAgentActivity.svelte';
	import type { DatabaseMessage } from '../../src/lib/types/database';
	let { message }: { message: DatabaseMessage } = $props();
</script>

<SpeedAgentActivity {message}>
	{#if message.content}<p data-final-response>{message.content}</p>{/if}
</SpeedAgentActivity>
