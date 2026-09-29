import Image from 'next/image';
import type { ReactNode } from 'react';

import { PHOTOS, type PhotoKey } from '@/lib/photos';

/**
 * تیتر عکس‌دار بالای صفحات پرتکرار اپ — بازطراحی بصری فاز ۳ (نقشهٔ راه §13.2).
 *
 * همان زبان بصری صفحهٔ اصلی («پژوهش و داده»)، ولی فشرده‌تر: این بنر بالای
 * صفحه‌ای می‌نشیند که هر روز دیده می‌شود، نه یک بخش تبلیغاتی یک‌بار-دیده.
 */
export function PageBanner({
  photo,
  title,
  description,
  actions,
}: {
  photo: PhotoKey;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  const image = PHOTOS[photo];
  return (
    <header className="grid overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div className="relative h-36 sm:h-auto">
        <Image
          src={image.src}
          alt={image.alt}
          fill
          sizes="(min-width: 640px) 40vw, 100vw"
          className="object-cover"
        />
      </div>
      <div className="flex flex-wrap items-end justify-between gap-4 p-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">{title}</h1>
          <p className="text-[14px] text-[var(--fg-secondary)]">{description}</p>
        </div>
        {actions}
      </div>
    </header>
  );
}
