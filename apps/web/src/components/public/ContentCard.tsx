import Link from 'next/link';

import type { ContentCard as Card } from '@/lib/api/content';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { CoverImage } from './CoverImage';

/**
 * کارت یک محتوا — فهرست مطالب، صفحهٔ اصلی و «مطالب مرتبط».
 * محتوای قفل‌شده هم دیده می‌شود (عنوان و خلاصه) با نشان دسترسی؛ متنش نه.
 */
export function ContentCard({
  item,
  featured = false,
  priority = false,
  as: Heading = 'h3',
}: {
  item: Card;
  featured?: boolean;
  priority?: boolean;
  /** سطح عنوان کارت: زیر `h1` صفحه `h2`، زیر یک بخش `h2` همان `h3` (ترتیب عنوان‌ها برای صفحه‌خوان). */
  as?: 'h2' | 'h3';
}) {
  return (
    <article className="group relative flex h-full flex-col overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] transition duration-[var(--dur-normal)] hover:-translate-y-0.5 hover:shadow-[var(--shadow-lg)]">
      <div
        className={`relative w-full overflow-hidden ${featured ? 'aspect-[16/9] md:aspect-[21/9]' : 'aspect-[16/10]'}`}
      >
        <CoverImage
          cover={item.cover}
          kind={item.kind}
          sizes={featured ? '(min-width: 1024px) 66vw, 100vw' : '(min-width: 1024px) 33vw, 100vw'}
          priority={priority}
          className="transition-transform duration-[var(--dur-slow)] group-hover:scale-[1.04]"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-transparent"
        />
        <span className="absolute start-3 top-3 rounded-full bg-black/55 px-3 py-1 text-[12px] font-medium text-white backdrop-blur">
          {item.kind_fa}
        </span>
        {item.access !== 'PUBLIC' && (
          <span className="absolute end-3 top-3 rounded-full bg-[var(--accent-500)] px-3 py-1 text-[12px] font-semibold text-[var(--neutral-900)]">
            {item.locked ? '🔒 ' : ''}
            {item.access_fa}
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-5">
        <Heading className={featured ? 'text-[22px] leading-[1.5]' : 'text-[17px] leading-[1.6]'}>
          {/* لینک کش کل کارت را کلیک‌پذیر می‌کند و برای صفحه‌خوان فقط یک پیوند می‌ماند. */}
          <Link
            href={`/content/${encodeURIComponent(item.slug)}`}
            className="after:absolute after:inset-0 after:content-['']"
          >
            {item.title_fa}
          </Link>
        </Heading>
        <p className="line-clamp-3 text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
          {item.summary}
        </p>
        <p className="mt-auto pt-2 text-[12.5px] text-[var(--fg-tertiary)]">
          {toPersianDigits(item.reading_minutes)} دقیقه مطالعه
          {item.published_at && ` · ${formatDateLong(item.published_at)}`}
        </p>
      </div>
    </article>
  );
}
