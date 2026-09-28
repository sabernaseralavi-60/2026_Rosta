'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { errorText, ErrorLine, StatTile } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import {
  fetchOverview,
  KIND_LABELS,
  NEED_TYPE_LABELS,
  type Overview,
  STATUS_LABELS,
  STATUS_TONES,
} from '@/lib/api/inbox';
import { useSession } from '@/lib/auth/use-session';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin/owner` — داشبورد مالک (ADR-0032، فایل مشخصات فاز ۰ بند ۲۶).
 *
 * طراحی استثنامحور، مثل شاخص‌های کلان: آنچه منتظر تو است بالا و رنگی؛ بقیه برای آگاهی.
 * فقط شاخص‌هایی هست که از داده‌های واقعی می‌آید؛ بخش‌هایی از مشخصات (پژوهش، فرصت‌های
 * تجاری، توصیه‌های AI) تا ساخته‌شدنِ داده‌شان اینجا نیستند، نه با عددِ ساختگی.
 */
export function OwnerDashboardView() {
  const { accessToken } = useSession();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchOverview(accessToken)
      .then(setData)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!data) return <SkeletonCard label="در حال بارگذاری داشبورد مالک" />;

  const contentTotal = Object.values(data.content).reduce((sum, n) => sum + n, 0);
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>داشبورد مالک</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          آنچه منتظر تو است بالاتر آمده؛ عدد صفر یعنی صف خالی است.
        </p>
      </header>

      <section aria-labelledby="waiting" className="flex flex-col gap-3">
        <h2 id="waiting" className="text-[18px]">
          منتظر اقدام
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="مسئله / نیازِ جدید" value={data.intake.INTAKE.NEW} tone="warning" />
          <StatTile
            label="درخواست همکاریِ جدید"
            value={data.intake.COLLABORATION.NEW}
            tone="warning"
          />
          <StatTile
            label="نیاز به پیگیری"
            value={data.stale}
            tone="danger"
            hint="بیش از سه روز بی‌رسیدگی"
          />
          <StatTile
            label="قدیمی‌ترین بی‌پاسخ (روز)"
            value={data.oldest_new_days ?? 0}
            tone="warning"
            hint={data.oldest_new_days === null ? 'درخواست جدیدی نیست' : undefined}
          />
        </div>
        <Link href="/admin/inbox" className="text-[13.5px] font-medium text-[var(--fg-brand)]">
          رفتن به صندوق درخواست‌ها ←
        </Link>
      </section>

      {data.follow_up.length > 0 && (
        <section aria-labelledby="follow" className="flex flex-col gap-3">
          <h2 id="follow" className="text-[18px]">
            نیازمند پیگیری
          </h2>
          <ul className="flex flex-col gap-2">
            {data.follow_up.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/admin/inbox?q=${encodeURIComponent(item.tracking_code)}`}
                  className="block rounded-[var(--radius-md)] hover:bg-[var(--bg-sunken)]"
                >
                  <Card className="flex flex-wrap items-center gap-x-3 gap-y-1 p-3">
                    <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
                    <span className="text-[14.5px] font-semibold">{item.contact_name}</span>
                    <span className="text-[13px] text-[var(--fg-secondary)]">
                      {KIND_LABELS[item.kind]}
                      {item.need_type && ` (${NEED_TYPE_LABELS[item.need_type] ?? item.need_type})`}
                    </span>
                    <span className="font-mono text-[12.5px] text-[var(--fg-tertiary)]" dir="ltr">
                      {item.tracking_code}
                    </span>
                    <span className="ms-auto text-[12.5px] text-[var(--fg-tertiary)]">
                      آخرین رسیدگی {formatRelative(item.updated_at)}
                    </span>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="pipeline" className="flex flex-col gap-3">
        <h2 id="pipeline" className="text-[18px]">
          مشتریان و همکاران
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="ثبت‌شده در ۷ روز اخیر" value={data.new_7d} />
          <StatTile
            label="در حال بررسی"
            value={data.intake.INTAKE.IN_REVIEW + data.intake.COLLABORATION.IN_REVIEW}
          />
          <StatTile label="مشتری پذیرفته‌شده" value={data.clients_accepted} hint="هر فرد یک بار" />
          <StatTile
            label="همکار پذیرفته‌شده"
            value={data.collaborators_accepted}
            hint="هر فرد یک بار"
          />
        </div>
      </section>

      <section aria-labelledby="learning" className="flex flex-col gap-3">
        <h2 id="learning" className="text-[18px]">
          دانشجویان و آموزش
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="دانشجو" value={data.students_total} />
          <StatTile label="فعال در ۷ روز اخیر" value={data.students_active_7d} />
          <StatTile label="ثبت‌نام فعال در درس‌ها" value={data.enrollments_active} />
          <StatTile label="درس" value={data.courses_total} />
        </div>
      </section>

      <section aria-labelledby="content" className="flex flex-col gap-3">
        <h2 id="content" className="text-[18px]">
          محتوا
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="منتشرشده" value={data.content.PUBLISHED ?? 0} />
          <StatTile label="پیش‌نویس" value={data.content.DRAFT ?? 0} />
          <StatTile label="بایگانی" value={data.content.ARCHIVED ?? 0} />
        </div>
        <p className="text-[13px] text-[var(--fg-secondary)]">
          {contentTotal === 0
            ? 'هنوز محتوایی منتشر نشده. یادداشت را در Vault بنویس و با «vault push» بفرست.'
            : `جمعاً ${toPersianDigits(contentTotal)} یادداشت. محتوا از Vault شخصی‌ات منتشر می‌شود.`}
        </p>
      </section>
    </div>
  );
}
