import { request } from './api';
import type { TaskOptions } from './types';

class SpeedSession {
	private generation = 0;
	enabled = $state(false);
	token = $state('');
	ownerId = $state('');
	username = $state('');
	options = $state<TaskOptions>({ flow: 'document', demo_mode: false, input_path: 'fixtures/inspection-report.txt' });

	async login(username: string, password: string) {
		const generation = ++this.generation;
		const result = await request<{ access_token: string }>('auth/login', '', {
			method: 'POST', body: JSON.stringify({ username, password })
		});
		const user = await request<{ id: string; username: string }>('auth/me', result.access_token);
		if (generation !== this.generation) return;
		this.token = result.access_token;
		this.ownerId = user.id;
		this.username = user.username;
	}

	logout() {
		this.generation++;
		this.enabled = false;
		this.token = '';
		this.ownerId = '';
		this.username = '';
	}
}

// Separate backend auth domain from Snap auth. Credentials are memory-only.
export const speedSession = new SpeedSession();
