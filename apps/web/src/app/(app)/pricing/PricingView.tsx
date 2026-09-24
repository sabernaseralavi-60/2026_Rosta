'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type MySubscriptions,
  type Plan,
  fetchMySubscriptions,
  fetchPlans,
  requestSubscription,
} from '@/lib/api/subscriptions';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/pricing` — ADR-0009.
 *
 * صفحه با یک جملهٔ صریح شروع می‌شود: **دانشجوی درس لازم نیست چیزی
 * بخرد.** فروختن اشتراک به کسی که همان محتوا را رایگان دارد، بدترین
 * نوع فروش است.
 *
 * پرداخت درون سامانه انجام نمی‌شود (§02): این صفحه یک **درخواست** ثبت
 * می‌کند و بقیهٔ کار بیرون از سامانه است. متن دکمه همین را می‌گوید تا
 * کسی انتظار درگاه نداشته باشد.
 */

const STATUS_TONES = {
  PENDING: 'warning',
  ACTIVE: 'success',
  EXPIRED: 'neutral',
  CANCELLED: 'neutral',
} as const;

export function PricingView() {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [mine, setMine] = useState<MySubscriptions | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPlans(await fetchPlans(accessToken));
      if (accessToken) setMine(await fetchMySubscriptions(accessToken));
      setError(null);
    } catch (cause) {
      setError(messageFor(cause));
      setPlans([]);
    }
  }, [accessToken]);

  useEffect(() => {
    if (sessionLoading) return;
    void load();
  }, [load, sessionLoading]);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">اشتراک کتابخانه</h1>
        <p className="max-w-[64ch] text-[14.5px] leading-7 text-[var(--fg-secondary)]">
          محتوای هر درس برای دانشجویان همان درس <strong>رایگان</strong> است و به اشتراک نیازی
          ندارند. اشتراک برای کسانی است که دانشجوی درس نیستند ولی می‌خواهند کتاب‌ها و جزوه‌ها را
          داشته باشند.
        </p>
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {mine && mine.items.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">اشتراک‌های من</h2>
          <ul className="flex flex-col gap-3">
            {mine.items.map((subscription) => (
              <li key={subscription.id}>
                <Card className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[15px] font-semibold text-[var(--fg-primary)]">
                        {subscription.plan_title_fa}
                      </span>
                      <Badge tone={STATUS_TONES[subscription.status]}>
                        {subscription.status_fa}
                      </Badge>
                      {subscription.course_title_fa && (
                        <Badge tone="neutral">{subscription.course_title_fa}</Badge>
                      )}
                    </div>
                    <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                      تا {formatDateLong(subscription.ends_at)}
                      {subscription.status === 'ACTIVE' &&
                        ` · ${toPersianDigits(subscription.days_remaining)} روز مانده`}
                    </span>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">طرح‌ها</h2>

        {plans === null ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                accessToken={accessToken}
                alreadyCovered={plan.scope === 'ALL_COURSES' && (mine?.covers_all_courses ?? false)}
                onRequested={load}
              />
            ))}
          </ul>
        )}
      </section>

      <Card className="flex flex-col gap-2">
        <CardTitle>پرداخت چگونه انجام می‌شود؟</CardTitle>
        <CardDescription>
          در این مرحله پرداخت بیرون از سامانه انجام می‌شود. با ثبت درخواست، یک رسید «در انتظار
          تأیید» ساخته می‌شود و پس از بررسی پرداخت، اشتراک فعال می‌گردد.
        </CardDescription>
        <div className="mt-2">
          <Button variant="secondary" asChild>
            <Link href="/library">بازگشت به کتابخانه</Link>
          </Button>
        </div>
      </Card>
    </div>
  );
}

function PlanCard({
  plan,
  accessToken,
  alreadyCovered,
  onRequested,
}: {
  plan: Plan;
  accessToken: string | null;
  alreadyCovered: boolean;
  onRequested: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // طرح تک‌درسی بدون انتخاب درس معنا ندارد؛ خرید آن از صفحهٔ همان درس
  // شروع می‌شود، نه از اینجا.
  const needsCourse = plan.scope === 'SINGLE_COURSE';

  async function submit() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      await requestSubscription(accessToken, { plan_code: plan.code });
      setDone(true);
      await onRequested();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card className="flex h-full flex-col gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle>{plan.title_fa}</CardTitle>
          <Badge tone="neutral">{plan.scope_fa}</Badge>
        </div>

        <p className="text-[24px] font-bold text-[var(--fg-brand)]">{plan.price_fa}</p>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          برای {toPersianDigits(plan.duration_days)} روز
        </p>

        {plan.description && (
          <p className="text-[13.5px] leading-6 text-[var(--fg-secondary)]">{plan.description}</p>
        )}

        <div className="mt-auto flex flex-col gap-2">
          {alreadyCovered ? (
            <p className="text-[12.5px] text-[var(--fg-success)]">
              اشتراک فعال شما همهٔ دروس را پوشش می‌دهد.
            </p>
          ) : needsCourse ? (
            <Button variant="secondary" asChild>
              <Link href="/library">انتخاب درس</Link>
            </Button>
          ) : done ? (
            <p className="text-[12.5px] text-[var(--fg-success)]">
              درخواست ثبت شد؛ پس از تأیید پرداخت فعال می‌شود.
            </p>
          ) : (
            <Button onClick={submit} disabled={busy || !accessToken} fullWidth>
              ثبت درخواست
            </Button>
          )}
          {!accessToken && (
            <p className="text-[12.5px] text-[var(--fg-tertiary)]">
              برای ثبت درخواست باید وارد شوید.
            </p>
          )}
          {error && (
            <p role="alert" className="text-[12.5px] text-[var(--fg-danger)]">
              {error}
            </p>
          )}
        </div>
      </Card>
    </li>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
