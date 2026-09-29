export const DEMO_PRINCIPAL_ID = 'speed-demo-admin';

/** The demo marker is not a JWT and is accepted only by a demo-enabled backend. */
export function speedAuthHeaders(credential: string): Record<string, string> {
	if (credential === DEMO_PRINCIPAL_ID) return { 'X-Speed-Demo-User': DEMO_PRINCIPAL_ID };
	return credential ? { Authorization: `Bearer ${credential}` } : {};
}
