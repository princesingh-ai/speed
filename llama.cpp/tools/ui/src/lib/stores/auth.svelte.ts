import { browser } from '$app/environment';
import { SPEED_AUTH_TOKEN_LOCALSTORAGE_KEY } from '$lib/constants';
import { AuthService } from '$lib/services/auth.service';
import { speedSession } from '$lib/speed/session.svelte';
import type { SpeedAuthUser } from '$lib/types';

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated';

export class AuthStore {
	status = $state<AuthStatus>('checking');
	token = $state<string | null>(null);
	user = $state<SpeedAuthUser | null>(null);
	error = $state<string | null>(null);
	private initialized = false;
	private generation = 0;

	get isAuthenticated(): boolean {
		return this.status === 'authenticated' && Boolean(this.token && this.user);
	}

	get isChecking(): boolean {
		return this.status === 'checking';
	}

	async initialize(): Promise<void> {
		if (!browser || this.initialized) return;

		this.initialized = true;
		const generation = ++this.generation;
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

		const generation = ++this.generation;
		this.error = null;

		try {
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
		}

		this.token = null;
		this.user = null;
		this.status = status;
	}
}

export const authStore = new AuthStore();
