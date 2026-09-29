import { base } from '$app/paths';
import { API_AUTH, HEADERS } from '$lib/constants';
import { MimeTypeApplication } from '$lib/enums';
import type { SpeedAuthLoginResponse, SpeedAuthUser } from '$lib/types';

export class AuthService {
	static async login(username: string, password: string): Promise<SpeedAuthLoginResponse> {
		const response = await fetch(`${base}${API_AUTH.LOGIN}`, {
			cache: 'no-store',
			signal: AbortSignal.timeout(15000),
			body: JSON.stringify({ password, username }),
			headers: {
				[HEADERS.CONTENT_TYPE]: MimeTypeApplication.JSON
			},
			method: 'POST'
		});

		if (!response.ok) {
			throw new Error(await AuthService.parseErrorMessage(response));
		}

		const data = (await response.json()) as SpeedAuthLoginResponse;

		if (!data.access_token) {
			throw new Error('Authentication failed.');
		}

		return data;
	}

	static async me(token: string): Promise<SpeedAuthUser> {
		const response = await fetch(`${base}${API_AUTH.ME}`, {
			cache: 'no-store',
			signal: AbortSignal.timeout(15000),
			headers: {
				[HEADERS.AUTHORIZATION]: `${HEADERS.BEARER}${token}`
			}
		});

		if (!response.ok) {
			throw new Error(await AuthService.parseErrorMessage(response));
		}

		const user = await response.json() as SpeedAuthUser;
		if (!user.id || !user.username || !Array.isArray(user.roles)) {
			throw new Error('Invalid SPEED session. Please sign in again.');
		}
		return user;
	}

	private static async parseErrorMessage(response: Response): Promise<string> {
		return response.status === 401 ? 'Invalid username or password.' : 'Unable to sign in. Please try again.';
	}
}
