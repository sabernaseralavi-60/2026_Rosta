/**
 * پنل مدیریت — §5.12، FR-ADM-01/02، §6.5، M7-12، ADR-0017.
 *
 * قواعد امتیاز (M5)، صف ارسال و الگوهای پیام (M6) API آماده داشتند و
 * رابطشان به همین پنل موکول شده بود (§13.6)؛ همه اینجا کنار هم‌اند.
 */

import { ApiError, apiFetch } from './client';
import type { PointEntry } from './points';
import type { Certificate } from './public';

export type UserStatus = 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';

export const USER_STATUS_LABELS: Record<UserStatus, string> = {
  ACTIVE: 'فعال',
  SUSPENDED: 'معلق',
  DEACTIVATED: 'غیرفعال',
};

export const ROLE_LABELS: Record<string, string> = {
  GUEST: 'مهمان',
  PUBLIC_LEARNER: 'فراگیر عمومی',
  STUDENT: 'دانشجو',
  PROJECT_MEMBER: 'عضو پروژه',
  PROJECT_LEAD: 'مدیر پروژه',
  MENTOR: 'منتور',
  TA: 'دستیار آموزشی',
  INSTRUCTOR: 'استاد',
  COORDINATOR: 'مدیر آموزشی',
  SUPPORT: 'پشتیبانی',
  ADMIN: 'مدیر سامانه',
};

/**
 * نقش‌هایی که پنل مدیریت را می‌بینند؛ سرور هر مسیر را جداگانه می‌سنجد.
 * مدیر آموزشی فقط «درس‌ها و ارائه‌ها» را دارد (ADR-0020).
 */
export const ADMIN_AREA_ROLES = ['ADMIN', 'SUPPORT', 'COORDINATOR'];

/** پشتیبانی و مدیر — شاخص‌ها، کاربران، لاگ و صف‌ها. */
export const OPERATIONS_ROLES = ['ADMIN', 'SUPPORT'];

export function canSeeAdmin(roles: string[] | undefined | null): boolean {
  return (roles ?? []).some((role) => ADMIN_AREA_ROLES.includes(role));
}

/** صفحهٔ آغاز پنل برای این نقش‌ها: مدیر آموزشی شاخص‌ها را نمی‌بیند. */
export function adminHome(roles: string[] | undefined | null): string {
  return (roles ?? []).some((role) => OPERATIONS_ROLES.includes(role))
    ? '/admin'
    : '/admin/courses';
}

export interface AdminUser {
  id: string;
  name: string | null;
  username: string | null;
  mobile: string | null;
  email: string | null;
  status: UserStatus;
  roles: string[];
  is_public: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserPage {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface RoleGrant {
  code: string;
  title_fa: string;
  scope_type: string;
  scope_id: string | null;
  scope_label: string | null;
  granted_by_name: string | null;
  granted_at: string;
  expires_at: string | null;
}

export interface AuditEntry {
  id: string;
  action: string;
  action_fa: string;
  entity_type: string;
  entity_type_fa: string;
  entity_id: string | null;
  actor_id: string | null;
  actor_name: string | null;
  impersonated_by: string | null;
  impersonator_name: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AdminUserDetail extends AdminUser {
  grants: RoleGrant[];
  derived_roles: string[];
  points_total: number;
  level: number;
  projects_active: number;
  projects_completed: number;
  enrollments: number;
  certificates: number;
  recent_audit: AuditEntry[];
  can_impersonate: boolean;
  impersonation_blocked_reason: string | null;
}

export interface RoleOption {
  code: string;
  title_fa: string;
  scopes: ('GLOBAL' | 'OFFERING')[];
}

export interface Metrics {
  users_total: number;
  users_active_7d: number;
  users_new_7d: number;
  users_suspended: number;
  public_profiles: number;
  roles: Record<string, number>;
  projects: Record<string, number>;
  pending_deliverables: number;
  pending_research: number;
  pending_metrics: number;
  pending_outputs: number;
  outbox: Record<string, number>;
  certificates: number;
  audit_24h: number;
  impersonations_7d: number;
}

export interface Impersonation {
  access_token: string;
  expires_at: string;
  user_id: string;
  user_name: string | null;
  username: string | null;
  roles: string[];
}

export interface AuditFilters {
  user_id?: string;
  actor_id?: string;
  action?: string;
  entity_type?: string;
  since?: string;
  until?: string;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

// ── کاربران و نقش‌ها ──────────────────────────────────────────────────
export function fetchMetrics(token: string) {
  return apiFetch<Metrics>('/admin/metrics', { accessToken: token });
}

export function fetchUsers(
  token: string,
  filters: { q?: string; role?: string; status?: string; page?: number },
) {
  return apiFetch<AdminUserPage>(`/admin/users${query(filters)}`, { accessToken: token });
}

export function fetchUser(token: string, id: string) {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`, { accessToken: token });
}

export function setUserStatus(token: string, id: string, status: UserStatus, reason: string) {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}`, {
    method: 'PATCH',
    accessToken: token,
    body: { status, reason },
  });
}

export function fetchRoleOptions(token: string) {
  return apiFetch<RoleOption[]>('/admin/roles', { accessToken: token });
}

export function grantRole(
  token: string,
  id: string,
  grant: {
    role: string;
    scope_type: 'GLOBAL' | 'OFFERING';
    scope_id?: string;
    expires_at?: string;
  },
) {
  return apiFetch<AdminUserDetail>(`/admin/users/${id}/roles`, {
    method: 'POST',
    accessToken: token,
    body: grant,
  });
}

export function revokeRole(token: string, id: string, grant: RoleGrant) {
  return apiFetch<AdminUserDetail>(
    `/admin/users/${id}/roles/${grant.code}${query({
      scope_type: grant.scope_type,
      scope_id: grant.scope_id ?? undefined,
    })}`,
    { method: 'DELETE', accessToken: token },
  );
}

export function impersonate(token: string, id: string) {
  return apiFetch<Impersonation>(`/admin/users/${id}/impersonate`, {
    method: 'POST',
    accessToken: token,
  });
}

export function endImpersonation(token: string, userId: string) {
  return apiFetch<void>('/admin/impersonation/end', {
    method: 'POST',
    accessToken: token,
    body: { user_id: userId },
  });
}

// ── لاگ حسابرسی ────────────────────────────────────────────────────────
export function fetchAudit(token: string, filters: AuditFilters, cursor?: string | null) {
  return apiFetch<{ items: AuditEntry[]; next_cursor: string | null }>(
    `/admin/audit${query({ ...filters, cursor: cursor ?? undefined, limit: 50 })}`,
    { accessToken: token },
  );
}

/** خروجی CSV با توکن — پیوند ساده نمی‌تواند هدر `Authorization` بفرستد. */
export async function downloadAuditCsv(token: string, filters: AuditFilters): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? '/api/v1';
  const response = await fetch(`${base}/admin/audit/export${query(filters)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, {
      code: 'EXPORT_FAILED',
      message: 'خروجی لاگ ساخته نشد. کمی بعد دوباره تلاش کنید.',
      details: {},
      trace_id: response.headers.get('X-Trace-Id') ?? '',
    });
  }
  return response.blob();
}

// ── گواهی ─────────────────────────────────────────────────────────────
export function searchCertificates(token: string, filters: { code?: string; user_id?: string }) {
  return apiFetch<Certificate[]>(`/admin/certificates${query(filters)}`, { accessToken: token });
}

export function revokeCertificate(token: string, id: string, reason: string) {
  return apiFetch<Certificate>(`/admin/certificates/${id}/revoke`, {
    method: 'POST',
    accessToken: token,
    body: { reason },
  });
}

// ── قواعد امتیاز — FR-GAM-02، §9.9 ────────────────────────────────────
export interface PointRule {
  code: string;
  title_fa: string;
  category: 'LEARNING' | 'RESEARCH' | 'STARTUP' | 'COMMUNITY';
  base_points: string;
  formula: string | null;
  daily_cap: number | null;
  weekly_cap: number | null;
  term_cap: number | null;
  is_active: boolean;
  updated_at: string;
}

export interface PointRuleUpdate {
  title_fa?: string;
  base_points?: number;
  daily_cap?: number;
  weekly_cap?: number;
  term_cap?: number;
  clear_caps?: ('daily_cap' | 'weekly_cap' | 'term_cap')[];
  is_active?: boolean;
}

export function fetchPointRules(token: string) {
  return apiFetch<PointRule[]>('/admin/point-rules', { accessToken: token });
}

export function updatePointRule(token: string, code: string, patch: PointRuleUpdate) {
  return apiFetch<PointRule>(`/admin/point-rules/${code}`, {
    method: 'PATCH',
    accessToken: token,
    body: patch,
  });
}

export function recalculatePoints(
  token: string,
  body: { rule_code: string; since?: string; until?: string },
) {
  return apiFetch<{ rule_code: string; reversed: number; reawarded: number; users: number }>(
    '/admin/point-rules/recalculate',
    { method: 'POST', accessToken: token, body },
  );
}

/** دفتر کل یک کاربر، تازه‌ترین اول — §9.9. */
export function fetchUserPoints(token: string, userId: string, cursor?: string | null) {
  const search = `?limit=10${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`;
  return apiFetch<{ items: PointEntry[]; next_cursor: string | null }>(
    `/admin/users/${userId}/points${search}`,
    { accessToken: token },
  );
}

/** اصلاح با رکورد معکوس — ردیف اصلی پاک نمی‌شود (D-09). */
export function reversePointEntry(token: string, entryId: string, reason: string) {
  return apiFetch<PointEntry>(`/admin/point-entries/${entryId}/reverse`, {
    method: 'POST',
    accessToken: token,
    body: { reason },
  });
}

// ── صف ارسال و الگوها — §7.10، FR-MSG-03 ──────────────────────────────
export type OutboxStatus = 'QUEUED' | 'SENDING' | 'SENT' | 'FAILED' | 'DEAD';

export interface OutboxMessage {
  id: string;
  channel: string;
  recipient_masked: string;
  template: string;
  priority: string;
  status: OutboxStatus;
  status_fa: string;
  attempts: number;
  next_attempt_at: string;
  last_error: string | null;
  user_id: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface OutboxPage {
  items: OutboxMessage[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  counts: Partial<Record<OutboxStatus, number>>;
}

export interface MessageTemplate {
  code: string;
  channel: string;
  kind_title_fa: string | null;
  subject: string | null;
  body: string;
  variables: string[];
  is_active: boolean;
  updated_at: string;
}

export function fetchOutbox(
  token: string,
  filters: { status?: OutboxStatus; channel?: string; page?: number },
) {
  return apiFetch<OutboxPage>(`/admin/outbox${query(filters)}`, { accessToken: token });
}

export function retryMessage(token: string, id: string) {
  return apiFetch<OutboxMessage>(`/admin/outbox/${id}/retry`, {
    method: 'POST',
    accessToken: token,
  });
}

export function retryDead(token: string, channel?: string) {
  return apiFetch<{ retried: number }>(`/admin/outbox/retry-dead${query({ channel })}`, {
    method: 'POST',
    accessToken: token,
  });
}

export function fetchTemplates(token: string) {
  return apiFetch<MessageTemplate[]>('/admin/message-templates', { accessToken: token });
}

export function saveTemplate(
  token: string,
  template: {
    code: string;
    channel: string;
    subject: string | null;
    body: string;
    is_active: boolean;
  },
) {
  return apiFetch<MessageTemplate>(
    `/admin/message-templates/${template.code}/${template.channel}`,
    {
      method: 'PUT',
      accessToken: token,
      body: { subject: template.subject, body: template.body, is_active: template.is_active },
    },
  );
}

export function previewTemplate(
  token: string,
  template: { code: string; channel: string; subject: string | null; body: string },
) {
  return apiFetch<{
    subject: string | null;
    body: string;
    length: number;
    sms_parts: number | null;
  }>('/admin/message-templates/preview', { method: 'POST', accessToken: token, body: template });
}
