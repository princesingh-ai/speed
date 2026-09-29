import type { TaskOptions } from './types';
import type { SpeedAuthUser } from '$lib/types';

class SpeedSession {
	enabled = $state(false);
	token = $state('');
	ownerId = $state('');
	username = $state('');
	options = $state<TaskOptions>({ flow: 'document', demo_mode: false, input_path: 'fixtures/inspection-report.txt' });

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

// AuthStore supplies the same verified SPEED identity used by chat.
export const speedSession = new SpeedSession();
