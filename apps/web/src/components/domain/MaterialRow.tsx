'use client';

import { useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Material, materialDownloadUrl } from '@/lib/api/courses';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * یک محتوا از کتابخانهٔ درس — ADR-0008 و ADR-0009.
 *
 * **محتوای قفل‌شده پنهان نمی‌شود.** عنوان، نویسنده و حجمش دیده می‌شود
 * و فقط دکمهٔ دانلود جایش را به توضیح قفل می‌دهد؛ کاربر باید بداند با
 * اشتراک چه چیزی باز می‌شود.
 *
 * متن قفل (`access.note_fa`) از سرور می‌آید و اینجا بازنویسی نمی‌شود:
 * قاعدهٔ «رایگان برای دانشجوی درس» یک‌جا نوشته شده است.
 */

const KIND_TONES: Record<string, BadgeTone> = {
  BOOK: 'brand',
  NOTE: 'neutral',
  SLIDE: 'info',
  VIDEO: 'accent',
  PODCAST: 'accent',
  DATASET: 'research',
  CODE: 'research',
  QUESTION_BANK: 'warning',
  LINK: 'neutral',
  OTHER: 'neutral',
};

const MB = 1024 * 1024;

export interface MaterialRowProps {
  material: Material;
  accessToken: string | null;
  /** نشانی صفحهٔ اشتراک — دکمهٔ قفل به اینجا می‌برد. */
  subscribeHref?: string;
}

export function MaterialRow({
  material,
  accessToken,
  subscribeHref = '/pricing',
}: MaterialRowProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { access } = material;

  async function handleDownload() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const ticket = await materialDownloadUrl(material.id, accessToken);
      // آدرس امضاشده کوتاه‌عمر است؛ همان لحظه باز می‌شود، ذخیره نمی‌شود.
      window.location.href = ticket.download_url;
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      className={cn(
        'flex flex-col gap-3 rounded-[var(--radius-lg)] border p-4',
        access.allowed
          ? 'border-[var(--border-subtle)] bg-[var(--bg-surface)]'
          : 'border-dashed border-[var(--border-default)] bg-[var(--bg-sunken)]',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={KIND_TONES[material.kind] ?? 'neutral'}>{material.kind_fa}</Badge>
            <h4 className="text-[15px] font-semibold text-[var(--fg-primary)]">
              {material.title_fa}
            </h4>
            {!access.allowed && (
              <Badge tone="neutral" icon={<LockIcon />}>
                {access.blocker === 'ENROLLMENT' ? 'ویژهٔ دانشجویان درس' : 'نیازمند اشتراک'}
              </Badge>
            )}
          </div>

          {material.description && (
            <p className="text-[13.5px] leading-6 text-[var(--fg-secondary)]">
              {material.description}
            </p>
          )}

          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            {[
              material.authors.length > 0 ? material.authors.join('، ') : null,
              material.edition,
              material.section,
              material.size_bytes
                ? `${toPersianDigits((material.size_bytes / MB).toFixed(1))} مگابایت`
                : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>

        <div className="shrink-0">
          {access.allowed ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={handleDownload}
              disabled={busy || !material.is_downloadable || !accessToken}
            >
              {busy ? 'در حال آماده‌سازی…' : 'دانلود'}
            </Button>
          ) : access.blocker === 'SUBSCRIPTION' ? (
            <Button size="sm" variant="primary" asChild>
              <a href={subscribeHref}>تهیهٔ اشتراک</a>
            </Button>
          ) : null}
        </div>
      </div>

      {/* متن دلیل — چه باز چه بسته. کاربر باید بداند چرا. */}
      <p
        className={cn(
          'text-[12.5px]',
          access.allowed ? 'text-[var(--fg-tertiary)]' : 'text-[var(--fg-secondary)]',
        )}
      >
        {access.note_fa}
      </p>

      {error && (
        <p role="alert" className="text-[12.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
    </li>
  );
}

function LockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="3.5" y="7" width="9" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
