<script lang="ts">
	let { onModelChange, model }: {
		onModelChange?: (id: string, name: string) => Promise<boolean>;
		model?: string;
	} = $props();
</script>

{#if onModelChange}
	<button onclick={() => onModelChange?.('model-id', 'Model name')}>Select model</button>
{:else}
	<span>{model}</span>
{/if}
