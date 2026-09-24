/** فراخوان‌های /subscriptions — ADR-0009. */

import { apiFetch } from './client';

export type PlanScope = 'ALL_COURSES' | 'SINGLE_COURSE';
export type SubscriptionStatus = 'PENDING' | 'ACTIVE' | 'EXPIRED' | 'CANCELLED';

export interface Plan {
  id: string;
  code: string;
  title_fa: string;
  description: string | null;
  scope: PlanScope;
  scope_fa: string;
  duration_days: number;
  price_irr: number;
  price_toman: number;
  /** قیمت آمادهٔ نمایش — «۱۹۹٬۰۰۰ تومان». کلاینت خودش قالب‌بندی نمی‌کند. */
  price_fa: string;
}

export interface Subscription {
  id: string;
  plan_code: string;
  plan_title_fa: string;
  course_id: string | null;
  course_title_fa: string | null;
  status: SubscriptionStatus;
  status_fa: string;
  starts_at: string;
  ends_at: string;
  days_remaining: number;
  payment_ref: string | null;
  amount_irr: number | null;
}

export interface MySubscriptions {
  has_active: boolean;
  covers_all_courses: boolean;
  items: Subscription[];
}

export function fetchPlans(accessToken?: string | null) {
  return apiFetch<Plan[]>('/subscriptions/plans', { accessToken });
}

export function fetchMySubscriptions(accessToken: string) {
  return apiFetch<MySubscriptions>('/subscriptions', { accessToken });
}

/**
 * ثبت درخواست اشتراک.
 *
 * پرداخت بیرون از سامانه انجام می‌شود (§02)، پس نتیجهٔ این فراخوان یک
 * ردیف «در انتظار تأیید» است، نه دسترسی باز.
 */
export function requestSubscription(
  accessToken: string,
  payload: { plan_code: string; course_slug?: string; note?: string },
) {
  return apiFetch<Subscription>('/subscriptions', {
    method: 'POST',
    accessToken,
    body: payload,
  });
}

export function cancelSubscription(subscriptionId: string, accessToken: string) {
  return apiFetch<Subscription>(`/subscriptions/${subscriptionId}`, {
    method: 'DELETE',
    accessToken,
  });
}

// ── پشتیبانی — ADR-0019 ──────────────────────────────────────────────
export interface AdminSubscription extends Subscription {
  user_id: string;
  user_name: string | null;
  username: string | null;
  /** کامل برای مدیر، پوشانده برای پشتیبانی. */
  user_mobile: string | null;
  note: string | null;
  created_at: string;
  granted_by_name: string | null;
  cancelled_at: string | null;
}

export const SUBSCRIPTION_STATUS_LABELS: Record<SubscriptionStatus, string> = {
  PENDING: 'در انتظار تأیید',
  ACTIVE: 'فعال',
  EXPIRED: 'منقضی',
  CANCELLED: 'لغو یا رد شده',
};

export function fetchAdminSubscriptions(
  accessToken: string,
  filters: { status?: SubscriptionStatus; user_id?: string } = {},
) {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.user_id) params.set('user_id', filters.user_id);
  const query = params.toString();
  return apiFetch<AdminSubscription[]>(`/subscriptions/admin${query ? `?${query}` : ''}`, {
    accessToken,
  });
}

/** دوره از لحظهٔ تأیید شمرده می‌شود؛ کد پیگیری الزامی است. */
export function activateSubscription(
  subscriptionId: string,
  paymentRef: string,
  accessToken: string,
) {
  return apiFetch<Subscription>(`/subscriptions/${subscriptionId}/activate`, {
    method: 'POST',
    body: { payment_ref: paymentRef },
    accessToken,
  });
}

export function rejectSubscription(subscriptionId: string, reason: string, accessToken: string) {
  return apiFetch<Subscription>(`/subscriptions/${subscriptionId}/reject`, {
    method: 'POST',
    body: { reason },
    accessToken,
  });
}

/** فیش دستی یا هدیه — بی کد پیگیری، علت در یادداشت لازم است. */
export function grantSubscription(
  accessToken: string,
  payload: {
    user_id: string;
    plan_code: string;
    course_slug?: string;
    payment_ref?: string;
    note?: string;
  },
) {
  return apiFetch<Subscription>('/subscriptions/grant', {
    method: 'POST',
    body: payload,
    accessToken,
  });
}
