'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { errorText, ErrorLine, StatTile } from '@/components/admin/common';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchMetrics, type Metrics, ROLE_LABELS } from '@/lib/api/admin';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin` — شاخص‌های کلان (§3.6). طراحی استثنامحور: آنچه منتظر کسی است
 * (صف‌های بررسی، پیام مرده) بالا و رنگی؛ بقیه برای آگاهی.
 */

const PROJECT_STATUS_LABELS: Record<string, string> = {
  DRAFT: 'پیش‌نویس',
  OPEN: 'باز',
  IN_PROGRESS: 'در جریان',
  PAUSED: 'متوقف',
  COMPLETED: 'تکمیل‌شده',
  CANCELLED: 'لغوشده',
};

export function MetricsView() {
  const { accessToken } = useSession();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchMetrics(accessToken)
      .then(setMetrics)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!metrics) return <SkeletonCard label="در حال بارگذاری شاخص‌ها" />;

  const dead = metrics.outbox.DEAD ?? 0;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>شاخص‌های کلان</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          آنچه منتظر اقدام است بالاتر آمده؛ عدد صفر یعنی صف خالی است.
        </p>
      </header>

      <section aria-labelledby="queues" className="flex flex-col gap-3">
        <h2 id="queues" className="text-[18px]">
          منتظر اقدام
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          <StatTile
            label="تحویل‌دادنی در انتظار بررسی"
            value={metrics.pending_deliverables}
            tone="warning"
          />
          <StatTile label="تحویل سطح پژوهش" value={metrics.pending_research} tone="warning" />
          <StatTile
            label="ادعای مقاله برای راستی‌آزمایی"
            value={metrics.pending_outputs}
            tone="warning"
          />
          <StatTile
            label="شاخص فروش در انتظار تأیید"
            value={metrics.pending_metrics}
            tone="warning"
          />
          <StatTile label="پیام ارسال‌نشدهٔ نهایی (DEAD)" value={dead} tone="danger" />
        </div>
        {dead > 0 && (
          <Link
            href="/admin/notifications"
            className="text-[13.5px] font-medium text-[var(--fg-brand)]"
          >
            رفتن به صف ارسال ←
          </Link>
        )}
      </section>

      <section aria-labelledby="people" className="flex flex-col gap-3">
        <h2 id="people" className="text-[18px]">
          کاربران
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          <StatTile label="همهٔ کاربران" value={metrics.users_total} />
          <StatTile label="ورود در ۷ روز گذشته" value={metrics.users_active_7d} />
          <StatTile label="ثبت‌نام در ۷ روز گذشته" value={metrics.users_new_7d} />
          <StatTile label="نیمرخ عمومی" value={metrics.public_profiles} />
          <StatTile label="معلق یا غیرفعال" value={metrics.users_suspended} />
        </div>
        <ul className="flex flex-wrap gap-2 text-[13px] text-[var(--fg-secondary)]">
          {Object.entries(metrics.roles)
            .sort(([, a], [, b]) => b - a)
            .map(([code, count]) => (
              <li
                key={code}
                className="rounded-[var(--radius-full)] bg-[var(--bg-sunken)] px-3 py-1"
              >
                {ROLE_LABELS[code] ?? code}: {toPersianDigits(count)}
              </li>
            ))}
        </ul>
      </section>

      <section aria-labelledby="work" className="flex flex-col gap-3">
        <h2 id="work" className="text-[18px]">
          پروژه‌ها، گواهی و امنیت
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {['OPEN', 'IN_PROGRESS', 'COMPLETED'].map((status) => (
            <StatTile
              key={status}
              label={`پروژهٔ ${PROJECT_STATUS_LABELS[status]}`}
              value={metrics.projects[status] ?? 0}
            />
          ))}
          <StatTile label="گواهی معتبر" value={metrics.certificates} />
          <StatTile
            label="مشاهده به‌عنوان کاربر (۷ روز)"
            value={metrics.impersonations_7d}
            hint={`${toPersianDigits(metrics.audit_24h)} رویداد حسابرسی در ۲۴ ساعت`}
          />
        </div>
      </section>
    </div>
  );
}
