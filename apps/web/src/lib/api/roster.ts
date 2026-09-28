/** فراخوان‌های ورود دانشجوی درس — ADR-0035. */

import type { LoginResult } from './auth';
import { apiFetch } from './client';

export interface RosterLookup {
  claim_id: string;
  /** «علی ر.» — نام کامل پیش از تأیید هویت نشان داده نمی‌شود. */
  display_name: string;
  has_email: boolean;
}

export interface RosterConfirm {
  cancelled: boolean;
  masked_email: string | null;
  expires_in: number;
  resend_after: number;
}

export interface RosterComplete extends LoginResult {
  is_new_user: boolean;
  courses: string[];
}

export function rosterLookup(mobile: string, studentNo: string) {
  return apiFetch<RosterLookup>('/public/roster/lookup', {
    method: 'POST',
    body: { mobile, student_no: studentNo },
  });
}

export function rosterConfirm(claimId: string, accept: boolean) {
  return apiFetch<RosterConfirm>('/public/roster/confirm', {
    method: 'POST',
    body: { claim_id: claimId, accept },
  });
}

export function rosterComplete(claimId: string, code: string, password: string) {
  return apiFetch<RosterComplete>('/public/roster/complete', {
    method: 'POST',
    body: { claim_id: claimId, code, password },
  });
}
