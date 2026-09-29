import { browser } from '$app/environment';
import { SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY, SPEED_DEMO_AUTH_LOCALSTORAGE_KEY } from '$lib/constants';
import { DEMO_PRINCIPAL_ID } from '$lib/speed/auth';
import { AuthService } from '$lib/services/auth.service';
import { speedSession } from '$lib/speed/session.svelte';
import type { SpeedAuthUser } from '$lib/types';

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated';

export class AuthStore {
	status = $state<AuthStatus>('checking');
	token = $state<string | null>(null);
	user = $state<SpeedAuthUser | null>(null);
	error = $state<string | null>(null);
	demoMode = $state(false);
	private initialized = false;
	private modeReady = false;
	private generation = 0;

	get isAuthenticated(): boolean {
		return this.status === 'authenticated' && Boolean(this.credential && this.user);
	}

	get credential(): string {
		return this.demoMode && this.user?.id === DEMO_PRINCIPAL_ID ? DEMO_PRINCIPAL_ID : this.token ?? '';
	}

	private restoreDemo(): void {
		this.error = null;
		this.token = null;
		this.user = { id: DEMO_PRINCIPAL_ID, username: 'admin', roles: ['admin'] };
		speedSession.setAuth(DEMO_PRINCIPAL_ID, this.user);
		this.status = 'authenticated';
	}

	get isChecking(): boolean {
		return this.status === 'checking';
	}

	async initialize(): Promise<void> {
		if (!browser || this.initialized) return;

		this.initialized = true;
		const generation = ++this.generation;
		try {
			const demoMode = await AuthService.configuration();
			if (generation !== this.generation) return;
			this.demoMode = demoMode;
			this.modeReady = true;
		} catch {
			if (generation !== this.generation) return;
			this.initialized = false;
			this.clearAuthState('unauthenticated');
			this.error = 'Unable to load sign-in mode. Reload to retry.';
			return;
		}
		if (this.demoMode) {
			localStorage.removeItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY);
			if (localStorage.getItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY) === 'admin') this.restoreDemo();
			else this.clearAuthState('unauthenticated');
			return;
		}
		localStorage.removeItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY);
		const storedToken = localStorage.getItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY)?.trim();

		if (!storedToken) {
			this.clearAuthState('unauthenticated');

			return;
		}

		this.status = 'checking';
		this.token = storedToken;

		try {
			const user = await AuthService.me(storedToken);
			if (generation !== this.generation) return;
			this.user = user;
			speedSession.setAuth(storedToken, this.user);
			this.error = null;
			this.status = 'authenticated';
		} catch {
			if (generation === this.generation) this.clearAuthState('unauthenticated');
		}
	}

	async login(username: string, password: string): Promise<void> {
		if (!browser) return;
		if (!this.initialized) await this.initialize();
		if (!this.initialized || !this.modeReady) throw new Error(this.error ?? 'Sign-in mode unavailable. Reload to retry.');

		const generation = ++this.generation;
		this.error = null;

		try {
			if (this.demoMode) {
				if (username !== 'admin' || password !== 'admin-password') {
					throw new Error('Invalid username or password.');
				}
				localStorage.setItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY, 'admin');
				this.restoreDemo();
				return;
			}
			const login = await AuthService.login(username, password);
			const token = login.access_token;
			const user = await AuthService.me(token);
			if (generation !== this.generation) throw new Error('Sign-in was cancelled.');

			localStorage.setItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY, token);
			this.token = token;
			this.user = user;
			speedSession.setAuth(token, this.user);
			this.status = 'authenticated';
		} catch (error) {
			if (generation === this.generation) {
				this.clearAuthState('unauthenticated');
				this.error = error instanceof Error ? error.message : 'Unable to sign in. Please try again.';
			}

			throw error;
		}
	}

	logout(): void {
		this.clearAuthState('unauthenticated');
	}

	handleUnauthorized(): void {
		this.clearAuthState('unauthenticated');
	}

	private clearAuthState(status: AuthStatus): void {
		this.generation++;
		speedSession.logout();
		if (browser) {
			localStorage.removeItem(SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY);
			localStorage.removeItem(SPEED_DEMO_AUTH_LOCALSTORAGE_KEY);
		}

		this.token = null;
		this.user = null;
		this.status = status;
	}
}

export const authStore = new AuthStore();
