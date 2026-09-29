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
import { speedSession } from '../../src/lib/speed/session.svelte';
import { request } from '../../src/lib/speed/api';
import { SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY } from '../../src/lib/constants';

const user = { id: 'user-admin', username: 'admin', roles: ['admin'] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
let app: ReturnType<typeof mount> | undefined;
let target: HTMLDivElement;

beforeEach(() => {
    authStore.logout();
    authStore.error = null;
    navigation.goto.mockReset();
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
        json(String(url).endsWith('/login') ? { access_token: 'verified-jwt', token_type: 'bearer' } : user)));
    target = document.createElement('div');
    document.body.append(target);
});
afterEach(async () => {
    if (app) await unmount(app);
    app = undefined;
    target.remove();
    authStore.logout();
    vi.unstubAllGlobals();
});

async function submit() {
    app = mount(LoginScreen, { target });
    await tick();
    const username = target.querySelector<HTMLInputElement>('#speed-username')!;
    const password = target.querySelector<HTMLInputElement>('#speed-password')!;
    username.value = 'admin';
    password.value = 'admin-password';
    username.dispatchEvent(new Event('input', { bubbles: true }));
    password.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    target.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

it('renders SPEED and submits development credentials to backend, then shares the verified session', async () => {
    await submit();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalledWith('#/', { replaceState: true }));
    expect(target.textContent).toContain('Sign in to SPEED');
    expect(target.textContent).toContain('Secure local AI workbench');
    expect(target.textContent).not.toMatch(/Snap|Connect to SPEED/);
    expect(fetch).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({
        method: 'POST', body: JSON.stringify({ password: 'admin-password', username: 'admin' })
    }));
    expect(localStorage.getItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY)).toBe('verified-jwt');
    expect(authStore.isAuthenticated).toBe(true);
    expect(speedSession.token).toBe(authStore.token);
    expect(speedSession.ownerId).toBe(user.id);
    await request('agent/tasks/owned', speedSession.token);
    expect(fetch).toHaveBeenLastCalledWith('/api/v1/agent/tasks/owned', expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer verified-jwt' })
    }));
    authStore.logout();
    expect(speedSession.token).toBe('');
    expect(authStore.user).toBeNull();
    expect(localStorage.getItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY)).toBeNull();
});

it('keeps invalid credentials inline, with no navigation or session', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ detail: 'private backend diagnostic' }, 401));
    await submit();
    await vi.waitFor(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Invalid username or password.'));
    expect(target.textContent).not.toContain('private backend diagnostic');
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(authStore.status).toBe('unauthenticated');
    expect(speedSession.token).toBe('');
});

it('blocks duplicate submissions while the request is pending', async () => {
    let finish!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    await submit();
    await tick();
    expect(target.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    target.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(fetch).toHaveBeenCalledTimes(1);
    finish(json({ access_token: 'verified-jwt' }));
    await vi.waitFor(() => expect(authStore.isAuthenticated).toBe(true));
});

it('verifies a restored token and clears expired agent auth', async () => {
    localStorage.setItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY, 'restored-jwt');
    const restored = new AuthStore();
    await restored.initialize();
    expect(restored.user).toEqual(user);
    expect(speedSession.token).toBe('restored-jwt');
    await authStore.login('admin', 'admin-password');
    vi.mocked(fetch).mockResolvedValue(json({}, 401));
    await expect(request('agent/tasks/owned', authStore.token!)).rejects.toThrow('Sign in to SPEED again.');
    expect(authStore.isAuthenticated).toBe(false);
    expect(speedSession.token).toBe('');
});

it('does not restore a session when logout occurs during verification', async () => {
    let finish!: (response: Response) => void;
    vi.mocked(fetch).mockResolvedValueOnce(json({ access_token: 'late-jwt' }))
        .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const pending = authStore.login('admin', 'admin-password');
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    authStore.logout();
    finish(json(user));
    await expect(pending).rejects.toThrow('Sign-in was cancelled.');
    expect(speedSession.token).toBe('');
    expect(localStorage.getItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY)).toBeNull();
});
