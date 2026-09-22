/** فراخوان‌های /auth — قرارداد §5.2. */

import { apiFetch } from './client';

export type Channel = 'SMS' | 'EMAIL';
export type OnboardingState =
  | 'BASIC_INFO_REQUIRED'
  | 'SURVEY_REQUIRED'
  | 'SURVEY_INCOMPLETE'
  | 'COMPLETE';

export interface OTPRequestResult {
  challenge_id: string;
  expires_in: number;
  resend_after: number;
  masked_destination: string;
}

export interface AuthUser {
  id: string;
  display_name: string | null;
  username: string | null;
  roles: string[];
  onboarding_state: OnboardingState;
}

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export function requestOtp(destination: string, channel: Channel = 'SMS') {
  return apiFetch<OTPRequestResult>('/auth/otp/request', {
    method: 'POST',
    body: { destination, channel, purpose: 'LOGIN' },
  });
}

export function verifyOtp(challengeId: string, code: string) {
  return apiFetch<LoginResult>('/auth/otp/verify', {
    method: 'POST',
    body: { challenge_id: challengeId, code },
  });
}

export function loginWithPassword(identifier: string, password: string) {
  return apiFetch<LoginResult>('/auth/login', {
    method: 'POST',
    body: { identifier, password },
  });
}

export function refreshTokens(refreshToken: string) {
  return apiFetch<Omit<LoginResult, 'user'>>('/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  });
}

export function logout(refreshToken: string) {
  return apiFetch<void>('/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  });
}
