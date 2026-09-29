/**
 * RouterService - Builds app route paths
 *
 * Returns chat route strings from a single source of truth (ROUTES). No state.
 */

import { ROUTES } from '$lib/constants';

export class RouterService {
	static authRedirect(authenticated: boolean, checking: boolean, routeId: string | null): string | null {
		if (checking) return null;
		if (!authenticated && routeId !== '/login') return ROUTES.LOGIN;
		if (authenticated && routeId === '/login') return ROUTES.START;
		return null;
	}

	static chat(id: string): string {
		return `${ROUTES.CHAT}/${id}`;
	}
}
