import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';

const navigation = vi.hoisted(() => ({ goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: navigation.goto }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/paths', () => ({ base: '' }));
vi.mock('$lib/stores', async () => {
	const { authStore } = await import('../../src/lib/stores/auth.svelte');
	return { authStore };
});
import LoginScreen from '../../src/lib/components/app/auth/LoginScreen.svelte';
import { authStore, AuthStore } from '../../src/lib/stores/auth.svelte';
import { AuthService } from '../../src/lib/services/auth.service';
import { RouterService } from '../../src/lib/services/router.service';
import { speedSession } from '../../src/lib/speed/session.svelte';
import { request } from '../../src/lib/speed/api';
import { speedAuthHeaders, DEMO_PRINCIPAL_ID } from '../../src/lib/speed/auth';
import { SPEED_DEMO_AUTH_LOCALSTORAGE_KEY, SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY } from '../../src/lib/constants';

let app: ReturnType<typeof mount> | undefined;
let target: HTMLDivElement;
beforeEach(async () => {
	authStore.logout();
	vi.spyOn(AuthService, 'configuration').mockResolvedValue(true);
	vi.spyOn(AuthService, 'login');
	vi.spyOn(AuthService, 'me');
	vi.stubGlobal('fetch', vi.fn(() => { throw new Error('Unexpected network call'); }));
	await authStore.initialize();
	navigation.goto.mockReset();
	target = document.createElement('div');
	document.body.append(target);
});
afterEach(async () => {
	if (app) await unmount(app);
	app = undefined;
	target.remove();
	authStore.logout();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

async function submit(username: string, password: string) {
	app = mount(LoginScreen, { target });
	await tick();
	for (const [id, value] of [['speed-username', username], ['speed-password', password]]) {
		const input = target.querySelector<HTMLInputElement>('#' + id)!;
		input.value = value;
		input.dispatchEvent(new Event('input', { bubbles: true }));
	}
	await tick();
	target.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
	await tick();
}

it('logs in locally, preserves SPEED branding and shares the fixed agent identity without a JWT', async () => {
	await submit('admin', 'admin-password');
	await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalledWith('#/', { replaceState: true }));
	expect(target.textContent).toContain('Sign in to SPEED');
	expect(target.textContent).not.toContain('Snap');
	expect(target.textContent).not.toContain('Connect to SPEED');
	expect(AuthService.login).not.toHaveBeenCalled();
	expect(AuthService.me).not.toHaveBeenCalled();
	expect(fetch).not.toHaveBeenCalled();
	expect(authStore.token).toBeNull();
	expect(speedSession.ownerId).toBe(DEMO_PRINCIPAL_ID);
	expect(localStorage.getItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY)).toBe('admin');
	expect(localStorage.getItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY)).toBeNull();
	expect(JSON.stringify(localStorage)).not.toContain('admin-password');
	vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ task_id: 'demo-task' })));
	await request('agent/tasks', speedSession.token, { method: 'POST', body: '{}' });
	expect(fetch).toHaveBeenCalledWith('/api/v1/agent/tasks', expect.objectContaining({
		headers: { 'Content-Type': 'application/json', 'X-Speed-Demo-User': DEMO_PRINCIPAL_ID }
	}));
	expect(speedAuthHeaders(authStore.credential)).not.toHaveProperty('Authorization');
});

it.each([['wrong', 'admin-password'], ['admin', 'wrong']])('rejects credentials locally: %s', async (username, password) => {
	await submit(username, password);
	await vi.waitFor(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Invalid username or password.'));
	expect(authStore.isAuthenticated).toBe(false);
	expect(navigation.goto).not.toHaveBeenCalled();
	expect(fetch).not.toHaveBeenCalled();
	expect(AuthService.login).not.toHaveBeenCalled();
	expect(AuthService.me).not.toHaveBeenCalled();
});

it('restores only demo state on refresh and clears it on logout with stable route guards', async () => {
	await authStore.login('admin', 'admin-password');
	const refreshed = new AuthStore();
	await refreshed.initialize();
	expect(refreshed.isAuthenticated).toBe(true);
	expect(RouterService.authRedirect(true, false, '/login')).toBe('#/');
	expect(RouterService.authRedirect(true, false, '/(chat)')).toBeNull();
	refreshed.logout();
	expect(localStorage.getItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY)).toBeNull();
	expect(speedSession.token).toBe('');
	expect(RouterService.authRedirect(false, false, '/(chat)')).toBe('#/login');
	expect(RouterService.authRedirect(false, false, '/login')).toBeNull();
	expect(AuthService.me).not.toHaveBeenCalled();
	expect(fetch).not.toHaveBeenCalled();
});

it('does not trust demo storage when the backend disables demo mode', async () => {
	localStorage.setItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY, 'admin');
	vi.mocked(AuthService.configuration).mockResolvedValue(false);
	const real = new AuthStore();
	await real.initialize();
	expect(real.isAuthenticated).toBe(false);
	expect(real.credential).toBe('');
	expect(localStorage.getItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY)).toBeNull();
});

it('fails closed if mode configuration cannot be loaded, without sending credentials', async () => {
	vi.mocked(AuthService.configuration).mockRejectedValue(new Error('Unavailable'));
	const unavailable = new AuthStore();
	await unavailable.initialize();
	await expect(unavailable.login('admin', 'admin-password')).rejects.toThrow('Unable to load sign-in mode');
	expect(unavailable.isAuthenticated).toBe(false);
	expect(AuthService.login).not.toHaveBeenCalled();
	expect(AuthService.me).not.toHaveBeenCalled();
	expect(fetch).not.toHaveBeenCalled();
});
