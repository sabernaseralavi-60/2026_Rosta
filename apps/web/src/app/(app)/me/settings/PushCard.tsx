'use client';

import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ApiError } from '@/lib/api/client';
import type { ChannelStatus, NotificationPreferences } from '@/lib/api/notifications';
import { toPersianDigits } from '@/lib/format/digits';
import {
  currentSubscription,
  disablePush,
  enablePush,
  notificationPermission,
  PushError,
  type PushSupport,
  pushSupport,
} from '@/lib/push/client';

/**
 * کارت «مرورگر و دستگاه» — ADR-0029، FR-MSG-02.
 *
 * فرقش با کارت پیام‌رسان‌ها: اینجا **نشانی ندارد و حساب پیوند نمی‌شود**؛
 * اشتراک به همین مرورگر گره است. پس دو وضعیت جدا نشان می‌دهد: «روی چند
 * دستگاه فعال است» (سرور) و «روی این دستگاه روشن است» (مرورگر).
 */

export function PushCard({
  status,
  publicKey,
  token,
  reload,
}: {
  status: ChannelStatus;
  publicKey: string | null;
  token: string;
  reload: () => Promise<NotificationPreferences | null>;
}) {
  const [support, setSupport] = useState<PushSupport>('supported');
  const [permission, setPermission] =
    useState<ReturnType<typeof notificationPermission>>('default');
  const [here, setHere] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setSupport(pushSupport());
    setPermission(notificationPermission());
    setHere((await currentSubscription()) !== null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      await reload();
    } catch (cause) {
      setMessage(
        cause instanceof PushError || cause instanceof ApiError
          ? cause.message
          : 'انجام نشد. دوباره تلاش کن.',
      );
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  const canEnable = support === 'supported' && publicKey !== null && permission !== 'denied';

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[15px] font-semibold">{status.title_fa}</span>
        <span
          className={
            'rounded-[var(--radius-full)] px-2 py-0.5 text-[12px] ' +
            (status.linked
              ? 'bg-[var(--brand-50)] text-[var(--fg-brand)]'
              : 'bg-[var(--bg-sunken)] text-[var(--fg-secondary)]')
          }
        >
          {status.linked ? 'فعال' : 'خاموش'}
        </span>
      </div>

      <p className="text-[13.5px] text-[var(--fg-secondary)]">
        {status.devices > 0
          ? `روی ${toPersianDigits(String(status.devices))} دستگاه روشن است${here === false ? '؛ این دستگاه جزوشان نیست.' : '.'}`
          : 'اعلان را مثل یک پیام‌رسان، روی خود دستگاه ببین — حتی وقتی سایت باز نیست.'}
      </p>

      {support === 'needs-install' && (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          در آیفون اول سایت را به صفحهٔ اصلی اضافه کن (دکمهٔ اشتراک‌گذاری ← «Add to Home Screen»)،
          بعد از داخل همان برنامه اینجا را باز کن و روشنش کن.
        </p>
      )}
      {support === 'unsupported' && (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          این مرورگر اعلان وب را پشتیبانی نمی‌کند.
        </p>
      )}
      {support === 'supported' && permission === 'denied' && (
        <p role="status" className="text-[13px] text-[var(--fg-secondary)]">
          مرورگر اعلان این سایت را مسدود کرده. از تنظیمات سایت در مرورگر آزادش کن، بعد اینجا روشنش
          کن.
        </p>
      )}

      {here === true ? (
        <Button
          variant="ghost"
          size="sm"
          className="self-start"
          loading={busy}
          onClick={() => void run(() => disablePush(token))}
        >
          خاموش کردن در این دستگاه
        </Button>
      ) : (
        <Button
          size="sm"
          className="self-start"
          loading={busy}
          disabled={!canEnable || here === null}
          onClick={() => publicKey && void run(() => enablePush(token, publicKey))}
        >
          روشن کردن در این دستگاه
        </Button>
      )}

      {message && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {message}
        </p>
      )}
    </Card>
  );
}
