import { afterEach, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import '../../src/app.css';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/paths', () => ({ base: '' }));
import SpeedControls from '../../src/lib/components/app/chat/SpeedAgent/SpeedControls.svelte';
import { AuthStore } from '../../src/lib/stores/auth.svelte';
import { AuthService } from '../../src/lib/services/auth.service';
import { speedSession } from '../../src/lib/speed/session.svelte';

let app: ReturnType<typeof mount> | undefined;
let target: HTMLDivElement | undefined;
let auth: AuthStore | undefined;
afterEach(async () => {
	if (app) await unmount(app);
	target?.remove();
	auth?.logout();
	speedSession.options.flow = 'document';
	vi.restoreAllMocks();
});

it('restores pointer interaction under the composer overlay and exposes controls after local demo login', async () => {
	vi.spyOn(AuthService, 'configuration').mockResolvedValue(true);
	const login = vi.spyOn(AuthService, 'login');
	const me = vi.spyOn(AuthService, 'me');
	auth = new AuthStore();
	await auth.initialize();
	await auth.login('admin', 'admin-password');
	speedSession.enabled = false;
	speedSession.options.flow = 'document';
	expect(auth.isAuthenticated).toBe(true);
	expect(speedSession.ownerId).toBe('speed-demo-admin');
	target = document.createElement('div');
	// Match the inherited pointer gate in ChatScreen, outside the nested ChatForm.
	target.style.pointerEvents = 'none';
	document.body.append(target);
	app = mount(SpeedControls, { target });
	await tick();
	const checkbox = target.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
	expect(checkbox.disabled).toBe(false);
	expect(getComputedStyle(checkbox).pointerEvents).toBe('auto');
	checkbox.scrollIntoView({ block: 'center' });
	const rect = checkbox.getBoundingClientRect();
	expect(document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)).toBe(checkbox);
	expect(target.querySelector('select')).toBeNull();
	checkbox.click();
	await tick();
	expect(speedSession.enabled).toBe(true);
	expect(target.querySelector('details')!.open).toBe(true);
	const select = target.querySelector<HTMLSelectElement>('select')!;
	expect(select.value).toBe('document');
	expect(select.getClientRects().length).toBeGreaterThan(0);
	select.value = 'mcp';
	select.dispatchEvent(new Event('change', { bubbles: true }));
	await tick();
	expect(speedSession.options.flow).toBe('mcp');
	checkbox.click();
	await tick();
	expect(speedSession.enabled).toBe(false);
	expect(target.querySelector('select')).toBeNull();
	expect(target.querySelector('input[type="password"]')).toBeNull();
	expect(login).not.toHaveBeenCalled();
	expect(me).not.toHaveBeenCalled();
});
