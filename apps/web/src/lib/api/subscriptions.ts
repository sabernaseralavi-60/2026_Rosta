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
