import Link from 'next/link';

import { CATEGORIES, CATEGORY_LABELS, type PointCategory, points } from '@/lib/api/points';
import { cn } from '@/lib/cn';
import { formatNumber } from '@/lib/format/digits';

/**
 * چهار دستهٔ امتیاز — §9.1. ردیف کاشی، نه نمودار.
 *
 * «این چهار دسته جدا از هم جمع می‌شوند و هرگز با هم ترکیب نمی‌گردند»؛ پس
 * نمودار سهم (کل = ۱۰۰٪) پیام غلط می‌دهد. چهار عدد مستقل، چهار کاشی.
 *
 * رنگ دسته فقط روی نشانگر کنار برچسب است؛ متن رنگ خنثی دارد (رنگ
 * زعفرانی و سبز روی سطح روشن کنتراست متن کافی ندارند). ترتیب کاشی‌ها
 * `CATEGORIES` است تا آبی و بنفش مجاور نشوند.
 *
 * هر کاشی پیوندی است به دفتر کل با فیلتر همان دسته — §9.10 شفافیت.
 */

const DOT: Record<PointCategory, string> = {
  LEARNING: 'bg-[var(--cat-learning)]',
  RESEARCH: 'bg-[var(--cat-research)]',
  STARTUP: 'bg-[var(--cat-startup)]',
  COMMUNITY: 'bg-[var(--cat-community)]',
};

export function CategoryDot({ category }: { category: PointCategory }) {
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block size-2.5 shrink-0 rounded-[var(--radius-full)]', DOT[category])}
    />
  );
}

export function CategoryTiles({
  totals,
  caption,
}: {
  totals: Record<PointCategory, string>;
  caption?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      {caption && <p className="text-[13px] text-[var(--fg-secondary)]">{caption}</p>}
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {CATEGORIES.map((category) => (
          <li key={category}>
            <Link
              href={`/me/points?category=${category}`}
              className="flex flex-col gap-1 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 transition-colors hover:border-[var(--border-default)]"
            >
              <span className="flex items-center gap-1.5 text-[12.5px] text-[var(--fg-secondary)]">
                <CategoryDot category={category} />
                {CATEGORY_LABELS[category]}
              </span>
              <span className="text-[20px] font-semibold text-[var(--fg-primary)]">
                {formatNumber(points(totals[category]))}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
