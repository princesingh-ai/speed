import { expect, it } from 'vitest';
import { RouterService } from '../../src/lib/services/router.service';

it('uses hash routes for authentication without redirecting an already settled route', () => {
	expect(RouterService.authRedirect(false, true, '/(chat)')).toBeNull();
	expect(RouterService.authRedirect(false, false, '/(chat)')).toBe('#/login');
	expect(RouterService.authRedirect(false, false, '/(chat)/chat/[id]')).toBe('#/login');
	expect(RouterService.authRedirect(false, false, '/login')).toBeNull();
	expect(RouterService.authRedirect(true, false, '/login')).toBe('#/');
	expect(RouterService.authRedirect(true, false, '/(chat)')).toBeNull();
	expect(RouterService.chat('existing')).toBe('#/chat/existing');
});
