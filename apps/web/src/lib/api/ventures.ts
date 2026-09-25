/**
 * فراخوان‌های /ventures، شاخص‌ها و دعوت به تیم — §5.8، FR-VEN-01/02، FR-TEAM-03 (M7).
 *
 * متن فارسی مرحله، شاخص و معیار خروج از **سرور** می‌آید (`stage_fa`،
 * `metric_fa`، `criteria[].text`) و اینجا بازسازی نمی‌شود.
 */

import { apiFetch } from './client';
import type { Page } from './projects';

export type VentureStage =
  'IDEA' | 'VALIDATION' | 'MVP' | 'FIRST_REVENUE' | 'GROWTH' | 'PAUSED' | 'CLOSED';
export type StageAction = 'ADVANCE' | 'PAUSE' | 'RESUME' | 'CLOSE';
export type MetricKind =
  'CALLS' | 'MEETINGS' | 'LEADS' | 'SALES_COUNT' | 'SALES_AMOUNT' | 'CONTENT_PIECES' | 'CUSTOMERS';
export type MetricStatus = 'PENDING' | 'VERIFIED' | 'REJECTED';

export const GROWTH_STAGES: VentureStage[] = [
  'IDEA',
  'VALIDATION',
  'MVP',
  'FIRST_REVENUE',
  'GROWTH',
];

export interface VentureMember {
  user_id: string;
  name: string | null;
  username: string | null;
  is_founder: boolean;
  joined_at: string;
}

export interface VentureSummary {
  id: string;
  slug: string;
  name: string;
  pitch: string;
  stage: VentureStage;
  stage_fa: string;
  founder: VentureMember | null;
  looking_for_cofounder: boolean;
  needed_roles: string[];
  member_count: number;
  created_at: string;
}

export interface Criterion {
  code: string;
  text: string;
  met: boolean;
  current: number;
  target: number;
}

export interface Readiness {
  next_stage: VentureStage | null;
  next_stage_fa: string | null;
  ready: boolean;
  criteria: Criterion[];
}

export interface StageChange {
  id: string;
  from_stage: VentureStage;
  to_stage: VentureStage;
  from_stage_fa: string;
  to_stage_fa: string;
  reason: string | null;
  changed_by_name: string | null;
  created_at: string;
}

export interface MetricTotals {
  verified: Partial<Record<MetricKind, number>>;
  pending: Partial<Record<MetricKind, number>>;
}

export interface VentureDetail extends VentureSummary {
  description: string | null;
  problem: string | null;
  target_market: string | null;
  revenue_model: string | null;
  current_status: string | null;
  paused_from_stage: VentureStage | null;
  stage_changed_at: string;
  origin_idea_id: string | null;
  members: VentureMember[];
  projects: { id: string; title_fa: string; status: string; kind: string }[];
  history: StageChange[];
  /** فقط برای اعضا و مدیران — دادهٔ فروش عمومی نیست. */
  readiness: Readiness | null;
  totals: MetricTotals | null;
  is_member: boolean;
  can_manage: boolean;
}

export interface VentureInput {
  name: string;
  pitch: string;
  description: string | null;
  problem: string | null;
  target_market: string | null;
  revenue_model: string | null;
  current_status: string | null;
  looking_for_cofounder: boolean;
  needed_roles: string[];
}

export function fetchVentures(filters: {
  q?: string;
  stage?: VentureStage;
  looking_for_cofounder?: boolean;
  page?: number;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return apiFetch<Page<VentureSummary>>(`/ventures${query ? `?${query}` : ''}`);
}

export function fetchMyVentures(accessToken: string) {
  return apiFetch<VentureSummary[]>('/ventures/mine', { accessToken });
}

export function fetchVenture(id: string, accessToken?: string | null) {
  return apiFetch<VentureDetail>(`/ventures/${id}`, { accessToken });
}

export function createVenture(accessToken: string, input: VentureInput) {
  return apiFetch<VentureDetail>('/ventures', { method: 'POST', accessToken, body: input });
}

export function updateVenture(accessToken: string, id: string, input: VentureInput) {
  return apiFetch<VentureDetail>(`/ventures/${id}`, { method: 'PATCH', accessToken, body: input });
}

export function changeVentureStage(
  accessToken: string,
  id: string,
  action: StageAction,
  reason?: string,
) {
  return apiFetch<VentureDetail>(`/ventures/${id}/stage`, {
    method: 'POST',
    accessToken,
    body: { action, reason: reason || null },
  });
}

export function leaveVenture(accessToken: string, id: string) {
  return apiFetch<void>(`/ventures/${id}/leave`, { method: 'POST', accessToken });
}

export function removeVentureMember(
  accessToken: string,
  id: string,
  userId: string,
  reason: string,
) {
  return apiFetch<void>(`/ventures/${id}/members/${userId}/remove`, {
    method: 'POST',
    accessToken,
    body: { reason },
  });
}

// ── شاخص ──────────────────────────────────────────────────────────────
export interface Metric {
  id: string;
  venture_id: string | null;
  project_id: string | null;
  owner_title: string | null;
  user_id: string;
  user_name: string | null;
  metric: MetricKind;
  metric_fa: string;
  value: number;
  occurred_on: string;
  note: string | null;
  evidence_file_id: string | null;
  status: MetricStatus;
  status_fa: string;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  can_review: boolean;
  is_mine: boolean;
  /** فقط فروش تأییدشدهٔ پروژه — عکسی از لحظهٔ تأیید (ADR-0025). */
  share_percent: number | null;
  share_rial: number | null;
  created_at: string;
}

export interface MetricsPage {
  items: Metric[];
  totals: MetricTotals;
  by_member: (MetricTotals & { user_id: string; name: string | null; share_rial: number })[];
  metric_titles: Record<MetricKind, string>;
  /** درصد فعلی پروژه؛ `null` برای کسب‌وکار (سهم ندارد). */
  share_percent: number | null;
  share_total_rial: number;
}

export interface MetricInput {
  metric: MetricKind;
  value: number;
  occurred_on: string;
  note: string | null;
}

/** شاخص کسب‌وکار یا پروژهٔ عملیاتی — مسیرها هم‌شکل‌اند. */
export type MetricOwner = { kind: 'venture' | 'project'; id: string };

function ownerPath(owner: MetricOwner): string {
  return owner.kind === 'venture' ? `/ventures/${owner.id}` : `/projects/${owner.id}`;
}

export function fetchMetrics(accessToken: string, owner: MetricOwner) {
  return apiFetch<MetricsPage>(`${ownerPath(owner)}/metrics`, { accessToken });
}

export function recordMetric(accessToken: string, owner: MetricOwner, input: MetricInput) {
  return apiFetch<Metric>(`${ownerPath(owner)}/metrics`, {
    method: 'POST',
    accessToken,
    body: input,
  });
}

export function deleteMetric(accessToken: string, metricId: string) {
  return apiFetch<void>(`/metrics/${metricId}`, { method: 'DELETE', accessToken });
}

export function reviewMetric(
  accessToken: string,
  metricId: string,
  decision: 'VERIFIED' | 'REJECTED',
  note?: string,
) {
  return apiFetch<Metric>(`/metrics/${metricId}/review`, {
    method: 'POST',
    accessToken,
    body: { decision, note: note || null },
  });
}

export function fetchMetricReviewQueue(accessToken: string) {
  return apiFetch<Metric[]>('/metrics/review-queue', { accessToken });
}

// ── دعوت ──────────────────────────────────────────────────────────────
export interface Invitation {
  id: string;
  target_type: 'PROJECT' | 'VENTURE';
  target_id: string;
  target_title: string;
  href: string;
  inviter_name: string | null;
  invitee_name: string | null;
  message: string | null;
  role_title: string | null;
  source: 'DIRECT' | 'IDEA_PROMOTION' | 'OPENING';
  status: 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'CANCELLED';
  expires_at: string;
  created_at: string;
}

export function fetchMyInvitations(accessToken: string) {
  return apiFetch<Invitation[]>('/me/invitations', { accessToken });
}

export function inviteToTeam(
  accessToken: string,
  owner: MetricOwner,
  body: { username: string; message?: string | null },
) {
  return apiFetch<Invitation>(`${ownerPath(owner)}/invitations`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export function fetchVentureInvitations(accessToken: string, ventureId: string) {
  return apiFetch<Invitation[]>(`/ventures/${ventureId}/invitations`, { accessToken });
}

export function acceptInvitation(accessToken: string, id: string) {
  return apiFetch<{ target_type: 'PROJECT' | 'VENTURE'; target_id: string; href: string }>(
    `/invitations/${id}/accept`,
    { method: 'POST', accessToken },
  );
}

export function declineInvitation(accessToken: string, id: string) {
  return apiFetch<void>(`/invitations/${id}/decline`, { method: 'POST', accessToken });
}

export function cancelInvitation(accessToken: string, id: string) {
  return apiFetch<void>(`/invitations/${id}`, { method: 'DELETE', accessToken });
}

// ── گزارش درآمد شخصی — FR-VEN-03، ADR-0025 ──────────────────────────────
export interface RevenueLine {
  metric_id: string;
  project_id: string;
  project_title: string;
  occurred_on: string;
  value: number;
  share_percent: number;
  share_rial: number;
  note: string | null;
}

export interface RevenueMonth {
  year: number;
  month: number;
  /** «مهر ۱۴۰۵» — از سرور. */
  title: string;
  sales_rial: number;
  share_rial: number;
  lines: RevenueLine[];
}

export interface RevenueReport {
  months: RevenueMonth[];
  total_sales_rial: number;
  total_share_rial: number;
  pending_sales_rial: number;
  pending_count: number;
}

export function fetchRevenue(accessToken: string) {
  return apiFetch<RevenueReport>('/me/revenue', { accessToken });
}
