import type { TaskOptions } from './types';
import type { SpeedAuthUser } from '$lib/types';

class SpeedSession {
	enabled = $state(false);
	// Transport credential: a JWT in real-auth mode, or the fixed demo marker.
	token = $state('');
	ownerId = $state('');
	username = $state('');
	options = $state<TaskOptions>({ flow: 'document', input_path: 'fixtures/inspection-report.txt' });

	setAuth(token: string, user: SpeedAuthUser) {
		this.token = token;
		this.ownerId = user.id;
		this.username = user.username;
	}

	logout() {
		this.enabled = false;
		this.token = '';
		this.ownerId = '';
		this.username = '';
	}
}

// AuthStore supplies the same SPEED identity used by chat.
export const speedSession = new SpeedSession();
