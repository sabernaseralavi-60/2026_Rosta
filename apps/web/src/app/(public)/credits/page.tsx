import type { Metadata } from 'next';
import Image from 'next/image';

import credits from '../../../../public/photos/credits.json';
import { PHOTOS, type PhotoKey } from '@/lib/photos';

export const metadata: Metadata = {
  title: 'منبع عکس‌ها',
  description: 'سازنده و مجوز هر عکسی که در سایت به کار رفته است.',
};

type Credit = { title: string; artist: string; license: string; source: string };

/**
 * منبع و مجوز عکس‌ها — مجوزهای CC BY و CC BY-SA نام سازنده و پیوند مجوز را
 * لازم دارند. اگر عکسی را با عکس خودتان عوض کردید، ردیفش را در
 * `public/photos/credits.json` هم به‌روز کنید.
 */
export default function CreditsPage() {
  const entries = Object.entries(credits as Record<string, Credit>);
  return (
    <div className="page flex flex-col gap-8 py-10">
      <header className="flex flex-col gap-2">
        <h1>
          <span className="block text-[30px]">منبع عکس‌ها</span>
        </h1>
        <p className="max-w-[60ch] text-[15px] leading-[2] text-[var(--fg-secondary)]">
          عکس‌های این سایت از ویکی‌مدیا کامنز با مجوزهای آزاد است. سپاس از عکاسان.
        </p>
      </header>
      <ul className="grid gap-5 md:grid-cols-2">
        {entries.map(([key, credit]) => {
          const photo = PHOTOS[key as PhotoKey];
          return (
            <li
              key={key}
              className="flex flex-col overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]"
            >
              <div className="relative aspect-[16/9]">
                <Image src={photo.src} alt={photo.alt} fill sizes="50vw" className="object-cover" />
              </div>
              <div className="flex flex-col gap-1 p-5 text-[14px]">
                <p className="font-semibold" dir="ltr">
                  {credit.title}
                </p>
                <p className="text-[var(--fg-secondary)]">
                  عکاس: <span dir="ltr">{credit.artist}</span> · مجوز:{' '}
                  <span dir="ltr">{credit.license}</span>
                </p>
                <a
                  href={credit.source}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-fit font-medium text-[var(--fg-brand)]"
                >
                  صفحهٔ اصلی ←
                </a>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
