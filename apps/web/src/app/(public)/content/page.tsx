import type { Metadata } from 'next';
import Link from 'next/link';

import { ContentCard } from '@/components/public/ContentCard';
import { CONTENT_PAGE_SIZE, fetchContentList } from '@/lib/api/content';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * کتابخانهٔ مطالب — فایل مشخصات فاز ۰، بند ۷ و ۸.
 *
 * فیلترها پیوند ساده‌اند (بدون JS): نوع، موضوع و جست‌وجو در نشانی می‌مانند، پس
 * هر نتیجه قابل اشتراک و ایندکس است. صفحه بی‌ورود رندر می‌شود؛ قفل محتوا برای
 * کاربر واردشده در صفحهٔ خود مطلب باز می‌شود.
 */

export const revalidate = 60;

export const metadata: Metadata = {
  title: 'مطالب',
  description:
    'مقاله‌های آموزشی، خلاصهٔ کتاب و مقاله، مثال‌های حل‌شده و مطالعهٔ موردی در حمل‌ونقل، عمران و تحلیل داده.',
};

type Search = { kind?: string; topic?: string; q?: string; page?: string };

function href(current: Search, patch: Partial<Search>): string {
  const merged: Search = { ...current, ...patch };
  // تغییر فیلتر همیشه به صفحهٔ اول برمی‌گردد؛ فقط خودِ جابه‌جایی صفحه `page` می‌گذارد.
  if (!('page' in patch)) delete merged.page;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(merged)) {
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `/content?${text}` : '/content';
}

export default async function ContentIndexPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const current = await searchParams;
  const page = Math.max(1, Number.parseInt(current.page ?? '1', 10) || 1);
  const result = await fetchContentList({
    kind: current.kind,
    topic: current.topic,
    q: current.q,
    limit: CONTENT_PAGE_SIZE,
    offset: (page - 1) * CONTENT_PAGE_SIZE,
  });
  const data = result.ok ? result.data : null;
  const pages = data ? Math.ceil(data.total / CONTENT_PAGE_SIZE) : 0;
  const filtered = Boolean(current.kind || current.topic || current.q);

  return (
    <div className="page flex flex-col gap-8 py-10">
      <header className="flex flex-col gap-3">
        <h1>
          <span className="block text-[32px] leading-[1.4] md:text-[40px]">مطالب</span>
        </h1>
        <p className="max-w-[60ch] text-[15px] leading-[2] text-[var(--fg-secondary)]">
          مقاله‌های آموزشی، خلاصهٔ کتاب و مقاله، مثال‌های حل‌شده و مطالعهٔ موردی. مطالب تازه هر روز
          اضافه می‌شود.
        </p>
      </header>

      <form action="/content" method="get" role="search" className="flex max-w-[560px] gap-2">
        {current.kind && <input type="hidden" name="kind" value={current.kind} />}
        {current.topic && <input type="hidden" name="topic" value={current.topic} />}
        <label htmlFor="content-q" className="sr-only">
          جست‌وجو در مطالب
        </label>
        <input
          id="content-q"
          name="q"
          type="search"
          minLength={2}
          maxLength={80}
          defaultValue={current.q ?? ''}
          placeholder="جست‌وجو در مطالب…"
          className="h-11 flex-1 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 text-[15px]"
        />
        <button
          type="submit"
          className="h-11 rounded-[var(--radius-md)] bg-[var(--brand-600)] px-5 text-[14px] font-semibold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
        >
          جست‌وجو
        </button>
      </form>

      {data && data.kinds.length > 0 && (
        <nav aria-label="فیلتر نوع" className="flex flex-wrap gap-2">
          <Chip active={!current.kind} to={href(current, { kind: undefined })}>
            همه
          </Chip>
          {data.kinds.map((kind) => (
            <Chip
              key={kind.value}
              active={current.kind === kind.value}
              to={href(current, { kind: kind.value })}
            >
              {kind.label} <span className="opacity-60">{toPersianDigits(kind.count)}</span>
            </Chip>
          ))}
        </nav>
      )}

      {data && data.topics.length > 0 && (
        <nav aria-label="فیلتر موضوع" className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-[var(--fg-tertiary)]">موضوع:</span>
          {data.topics.slice(0, 12).map((topic) => (
            <Link
              key={topic.value}
              href={href(current, {
                topic: current.topic === topic.value ? undefined : topic.value,
              })}
              aria-current={current.topic === topic.value ? 'true' : undefined}
              className={`rounded-full px-3 py-1 ${
                current.topic === topic.value
                  ? 'bg-[var(--accent-100)] font-semibold text-[var(--fg-accent)]'
                  : 'bg-[var(--bg-sunken)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              {topic.label}
            </Link>
          ))}
        </nav>
      )}

      {result.ok && data && data.items.length > 0 ? (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(data.total)} مطلب
            {filtered && (
              <>
                {' · '}
                <Link href="/content" className="font-medium text-[var(--fg-brand)]">
                  پاک‌کردن فیلترها
                </Link>
              </>
            )}
          </p>
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((item, index) => (
              <li key={item.slug}>
                <ContentCard item={item} priority={index < 3} as="h2" />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--border-default)] p-12 text-center text-[15px] text-[var(--fg-secondary)]">
          {!result.ok
            ? 'اتصال به سرور برقرار نشد. کمی بعد دوباره امتحان کنید.'
            : filtered
              ? 'مطلبی با این فیلتر پیدا نشد.'
              : 'هنوز مطلبی منتشر نشده است.'}
        </div>
      )}

      {pages > 1 && (
        <nav aria-label="صفحه‌بندی" className="flex items-center justify-center gap-2 text-[14px]">
          {page > 1 && (
            <Link
              href={href(current, { page: String(page - 1) })}
              className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-4 py-2"
            >
              → قبلی
            </Link>
          )}
          <span className="px-3 text-[var(--fg-secondary)]">
            صفحهٔ {toPersianDigits(page)} از {toPersianDigits(pages)}
          </span>
          {page < pages && (
            <Link
              href={href(current, { page: String(page + 1) })}
              className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-4 py-2"
            >
              بعدی ←
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}

function Chip({
  active,
  to,
  children,
}: {
  active: boolean;
  to: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={to as never}
      aria-current={active ? 'true' : undefined}
      className={`rounded-full border px-4 py-2 text-[14px] font-medium transition-colors ${
        active
          ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
          : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)]'
      }`}
    >
      {children}
    </Link>
  );
}
