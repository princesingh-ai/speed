export interface SpeedAuthLoginResponse {
	access_token: string;
	token_type: 'bearer' | string;
}

export interface SpeedAuthUser {
	id: string;
	username: string;
	roles: string[];
}
