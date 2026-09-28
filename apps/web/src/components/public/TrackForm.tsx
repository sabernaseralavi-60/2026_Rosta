'use client';

import Link from 'next/link';
import { type FormEvent, useState } from 'react';

import { RequestTimeline } from '@/components/domain/RequestTimeline';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  CLIENT_STATUS_LABELS,
  KIND_LABELS,
  NEED_TYPE_LABELS,
  STATUS_TONES,
  trackRequest,
  type TrackResult,
} from '@/lib/api/inbox';
import { formatDateShort } from '@/lib/format/date';

/**
 * فرم پیگیری بی‌ورود — ADR-0032.
 *
 * پاسخ سرور فقط وضعیت و پیام‌های تیم است، نه متن درخواست (کد پیوسته است و شماره شاید لو
 * رفته باشد). خطا عمداً یکی است: «کد اشتباه» و «راه تماس اشتباه» از هم تشخیص داده نمی‌شوند.
 */
export function TrackForm() {
  const [code, setCode] = useState('');
  const [contact, setContact] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TrackResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await trackRequest(code.trim(), contact.trim()));
    } catch (cause) {
      if (cause instanceof ApiError && cause.isRateLimited) {
        setError('تلاش‌های زیادی شد. کمی بعد دوباره امتحان کنید.');
      } else if (cause instanceof ApiError || cause instanceof NetworkError) {
        setError(cause.message);
      } else {
        setError('درخواست انجام نشد. کمی بعد دوباره تلاش کنید.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Input
          label="کد پیگیری"
          hint="مثل Q-1001 یا C-1002"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          forceLtr
          autoComplete="off"
          required
        />
        <Input
          label="شمارهٔ موبایل یا ایمیلِ ثبت‌شده"
          value={contact}
          onChange={(event) => setContact(event.target.value)}
          forceLtr
          autoComplete="off"
          required
        />
        {error && (
          <p role="alert" className="text-[14px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div>
          <Button type="submit" loading={busy} disabled={!code.trim() || !contact.trim()}>
            پیگیری
          </Button>
        </div>
      </form>

      {result && (
        <Card className="flex flex-col gap-4 p-5" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONES[result.status]}>{CLIENT_STATUS_LABELS[result.status]}</Badge>
            <span className="text-[14px] text-[var(--fg-secondary)]">
              {KIND_LABELS[result.kind]}
              {result.need_type && ` (${NEED_TYPE_LABELS[result.need_type] ?? result.need_type})`}
            </span>
            <span className="font-mono text-[13px] text-[var(--fg-tertiary)]" dir="ltr">
              {result.tracking_code}
            </span>
          </div>
          <RequestTimeline
            createdAt={result.created_at}
            events={result.events}
            labels={CLIENT_STATUS_LABELS}
          />
          <p className="text-[13.5px] leading-[1.9] text-[var(--fg-secondary)]">
            ثبت شده در {formatDateShort(result.created_at)}. برای دیدن همهٔ درخواست‌هایتان یک‌جا،{' '}
            <Link href="/login" className="font-medium text-[var(--fg-brand)]">
              با همین شماره وارد شوید
            </Link>
            .
          </p>
        </Card>
      )}
    </div>
  );
}
