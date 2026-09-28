/**
 * صندوق درخواست‌های ورودی، داشبورد مالک و پیگیری مشتری — ADR-0032.
 *
 * مالک (`intake.manage`، نقش ADMIN) یادداشت خصوصی و راه تماس را می‌بیند؛ مشتری هیچ‌کدام
 * را: `MyRequest` و `TrackResult` عمداً فیلد `owner_note` و `contact_*` ندارند.
 */

import type { BadgeTone } from '@/components/ui/Badge';

import { apiFetch } from './client';

export type IntakeStatus = 'NEW' | 'IN_REVIEW' | 'ACCEPTED' | 'DECLINED' | 'ARCHIVED';
export type IntakeKind = 'INTAKE' | 'COLLABORATION';

export const STATUSES: IntakeStatus[] = ['NEW', 'IN_REVIEW', 'ACCEPTED', 'DECLINED', 'ARCHIVED'];

/** عنوان برای مالک (صندوق) — «جدید» از دید او. */
export const STATUS_LABELS: Record<IntakeStatus, string> = {
  NEW: 'جدید',
  IN_REVIEW: 'در حال بررسی',
  ACCEPTED: 'پذیرفته‌شده',
  DECLINED: 'ردشده',
  ARCHIVED: 'بایگانی',
};

/** عنوان برای مشتری — «جدید» برای او یعنی «دریافت شد». */
export const CLIENT_STATUS_LABELS: Record<IntakeStatus, string> = {
  NEW: 'دریافت شد',
  IN_REVIEW: 'در حال بررسی',
  ACCEPTED: 'پذیرفته شد',
  DECLINED: 'در حال حاضر امکان همکاری نیست',
  ARCHIVED: 'بسته شد',
};

export const STATUS_TONES: Record<IntakeStatus, BadgeTone> = {
  NEW: 'warning',
  IN_REVIEW: 'info',
  ACCEPTED: 'success',
  DECLINED: 'neutral',
  ARCHIVED: 'neutral',
};

export const KIND_LABELS: Record<IntakeKind, string> = {
  INTAKE: 'مسئله / نیاز',
  COLLABORATION: 'همکاری',
};

export const NEED_TYPE_LABELS: Record<string, string> = {
  Commercial: 'تجاری',
  Research: 'پژوهشی',
  Education: 'آموزشی',
  Consulting: 'مشاوره',
  Collaboration: 'همکاری',
  Other: 'سایر',
};

export interface IntakeEvent {
  id: string;
  from_status: IntakeStatus | null;
  to_status: IntakeStatus;
  public_note: string | null;
  created_at: string;
}

// ── مالک ───────────────────────────────────────────────────────────────
export interface InboxItem {
  id: string;
  kind: IntakeKind;
  tracking_code: string;
  status: IntakeStatus;
  contact_name: string;
  contact_mobile: string | null;
  contact_email: string | null;
  organization: string | null;
  need_type: string | null;
  services: string[];
  summary: string;
  person_code: string | null;
  created_at: string;
  updated_at: string;
  stale: boolean;
}

export interface InboxDetail extends InboxItem {
  payload: Record<string, unknown>;
  owner_note: string | null;
  events: IntakeEvent[];
}

export interface InboxPage {
  items: InboxItem[];
  total: number;
  counts: Record<IntakeStatus, number>;
}

export interface InboxFilters {
  kind?: IntakeKind;
  status?: IntakeStatus;
  q?: string;
  offset?: number;
}

export interface InboxUpdate {
  status?: IntakeStatus;
  /** رشتهٔ خالی یادداشت را پاک می‌کند؛ نبودن کلید = دست‌نخورده. */
  owner_note?: string;
  public_note?: string;
}

export const INBOX_PAGE_SIZE = 30;

export function fetchInbox(token: string, filters: InboxFilters = {}) {
  const params = new URLSearchParams({ limit: String(INBOX_PAGE_SIZE) });
  if (filters.kind) params.set('kind', filters.kind);
  if (filters.status) params.set('status', filters.status);
  if (filters.q && filters.q.trim().length >= 2) params.set('q', filters.q.trim());
  if (filters.offset) params.set('offset', String(filters.offset));
  return apiFetch<InboxPage>(`/admin/intake?${params}`, { accessToken: token });
}

export function fetchInboxItem(token: string, id: string) {
  return apiFetch<InboxDetail>(`/admin/intake/${id}`, { accessToken: token });
}

export function updateInboxItem(token: string, id: string, body: InboxUpdate) {
  return apiFetch<InboxDetail>(`/admin/intake/${id}`, {
    method: 'PATCH',
    accessToken: token,
    body,
  });
}

export interface Overview {
  intake: Record<IntakeKind, Record<IntakeStatus, number>>;
  new_7d: number;
  stale: number;
  oldest_new_days: number | null;
  students_total: number;
  students_active_7d: number;
  enrollments_active: number;
  courses_total: number;
  content: Record<string, number>;
  clients_accepted: number;
  collaborators_accepted: number;
  follow_up: InboxItem[];
}

export function fetchOverview(token: string) {
  return apiFetch<Overview>('/admin/owner/overview', { accessToken: token });
}

/** ADMIN — تنها نقشی که `intake.manage` دارد (ماتریس مجوز سرور). */
export function canManageInbox(roles: string[] | undefined | null): boolean {
  return (roles ?? []).includes('ADMIN');
}

// ── مشتری ──────────────────────────────────────────────────────────────
export interface MyRequest {
  tracking_code: string;
  kind: IntakeKind;
  status: IntakeStatus;
  need_type: string | null;
  services: string[];
  summary: string;
  created_at: string;
  updated_at: string;
  events: IntakeEvent[];
}

export function fetchMyRequests(token: string) {
  return apiFetch<MyRequest[]>('/me/requests', { accessToken: token });
}

export interface TrackResult {
  tracking_code: string;
  kind: IntakeKind;
  status: IntakeStatus;
  need_type: string | null;
  created_at: string;
  updated_at: string;
  events: IntakeEvent[];
}

export function trackRequest(trackingCode: string, contact: string) {
  return apiFetch<TrackResult>('/public/track', {
    method: 'POST',
    body: { tracking_code: trackingCode, contact },
  });
}
