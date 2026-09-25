'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonText } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  type ChannelStatus,
  confirmChannelLink,
  fetchPreferences,
  type LinkableChannel,
  type NotificationChannel,
  type NotificationGroup,
  type NotificationPreferences,
  savePreferences,
  startChannelLink,
  unlinkChannel,
} from '@/lib/api/notifications';
import { useSession } from '@/lib/auth/use-session';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

import { PushCard } from './PushCard';

/**
 * تنظیمات اعلان — FR-MSG-02، M6-09.
 *
 * دو بخش، به همین ترتیب: اول **کانال‌ها** (پیامک و ایمیل از حساب می‌آیند،
 * تلگرام و ایتا باید وصل شوند)، بعد **کدام خبر از کدام کانال**. «داخل
 * سامانه» همیشه روشن است — مرکز اعلان سابقهٔ همه‌چیز است.
 *
 * کانالی که نشانی ندارد، قابل انتخاب نیست: تیک زدن «تلگرام» پیش از وصل
 * کردنش، انتظاری می‌سازد که سامانه نمی‌تواند برآورده کند.
 */

const LINK_POLL_MS = 3_000;
const LINK_POLL_LIMIT_MS = 15 * 60_000;

export type Choices = Record<NotificationGroup, NotificationChannel[]>;

/** کانال‌هایی که کاربر می‌تواند برای یک دسته روشن یا خاموش کند. */
export function selectableChannels(channels: ChannelStatus[]): ChannelStatus[] {
  return channels.filter((c) => c.available);
}

export function canSelect(status: ChannelStatus): boolean {
  return status.available && status.linked;
}

export function toggle(
  choices: Choices,
  group: NotificationGroup,
  channel: NotificationChannel,
): Choices {
  if (channel === 'IN_APP') return choices;
  const current = choices[group];
  const next = current.includes(channel)
    ? current.filter((c) => c !== channel)
    : [...current, channel];
  return { ...choices, [group]: next };
}

function choicesOf(prefs: NotificationPreferences): Choices {
  return Object.fromEntries(prefs.groups.map((g) => [g.group, g.channels])) as Choices;
}

function sameChoices(a: Choices, b: Choices): boolean {
  return (Object.keys(a) as NotificationGroup[]).every(
    (group) => [...a[group]].sort().join() === [...(b[group] ?? [])].sort().join(),
  );
}

function hour(value: number): string {
  return toPersianDigits(String(value));
}

export function NotificationSettingsView() {
  const { accessToken, loading } = useSession();
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [choices, setChoices] = useState<Choices | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const apply = useCallback((next: NotificationPreferences) => {
    setPrefs(next);
    setChoices(choicesOf(next));
  }, []);

  const reload = useCallback(async () => {
    if (!accessToken) return null;
    const next = await fetchPreferences(accessToken);
    apply(next);
    return next;
  }, [accessToken, apply]);

  useEffect(() => {
    if (loading || !accessToken) return;
    reload().catch((cause: unknown) =>
      setError(cause instanceof ApiError ? cause.message : 'تنظیمات بارگذاری نشد.'),
    );
  }, [accessToken, loading, reload]);

  async function save() {
    if (!accessToken || !choices) return;
    setSaving(true);
    setSaved(false);
    try {
      apply(await savePreferences(accessToken, choices));
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'ذخیره نشد. دوباره تلاش کن.');
    } finally {
      setSaving(false);
    }
  }

  if (error && !prefs) return <EmptyState title="تنظیمات اعلان بارگذاری نشد" description={error} />;
  if (!prefs || !choices || !accessToken) return <SkeletonText label="در حال بارگذاری تنظیمات" />;

  const selectable = selectableChannels(prefs.channels);
  const dirty = !sameChoices(choices, choicesOf(prefs));
  const quiet = prefs.quiet_hours;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1>تنظیمات اعلان</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          همهٔ اعلان‌ها در سامانه می‌مانند. اینجا انتخاب می‌کنی کدام‌ها به پیامک، ایمیل یا پیام‌رسان
          هم بیایند.
        </p>
      </div>

      <section aria-labelledby="channels-heading" className="flex flex-col gap-3">
        <h2 id="channels-heading" className="text-[18px] font-semibold">
          کانال‌ها
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {selectable.map((status) =>
            status.channel === 'PUSH' ? (
              <PushCard
                key={status.channel}
                status={status}
                publicKey={prefs.push_public_key}
                token={accessToken}
                reload={reload}
              />
            ) : (
              <ChannelCard
                key={status.channel}
                status={status}
                token={accessToken}
                onChange={apply}
                reload={reload}
              />
            ),
          )}
        </div>
      </section>

      <section aria-labelledby="groups-heading" className="flex flex-col gap-3">
        <h2 id="groups-heading" className="text-[18px] font-semibold">
          کدام خبر، از کجا
        </h2>
        <Card className="flex flex-col divide-y divide-[var(--border-subtle)] p-0">
          {prefs.groups.map((group) => (
            <fieldset key={group.group} className="flex flex-col gap-3 px-5 py-4">
              <legend className="contents">
                <span className="text-[15px] font-semibold">{group.title_fa}</span>
              </legend>
              <p className="-mt-2 text-[13px] text-[var(--fg-secondary)]">{group.description_fa}</p>
              <div className="flex flex-wrap gap-2">
                <ChannelToggle
                  label="داخل سامانه"
                  checked
                  disabled
                  hint="همیشه روشن"
                  onChange={() => undefined}
                />
                {selectable.map((status) => (
                  <ChannelToggle
                    key={status.channel}
                    label={status.title_fa}
                    // کانالی که نشانی ندارد تیک‌خورده نشان داده نمی‌شود؛ چیزی آنجا نمی‌رود.
                    checked={canSelect(status) && choices[group.group].includes(status.channel)}
                    disabled={!canSelect(status)}
                    hint={
                      canSelect(status)
                        ? undefined
                        : status.channel === 'PUSH'
                          ? 'اول روشنش کن'
                          : status.requires_link
                            ? 'اول وصلش کن'
                            : 'نشانی نداری'
                    }
                    onChange={() => {
                      setSaved(false);
                      setChoices((current) =>
                        current ? toggle(current, group.group, status.channel) : current,
                      );
                    }}
                  />
                ))}
              </div>
            </fieldset>
          ))}
        </Card>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void save()} loading={saving} disabled={!dirty}>
            ذخیرهٔ تنظیمات
          </Button>
          <span role="status" className="text-[13.5px] text-[var(--fg-secondary)]">
            {saved ? 'ذخیره شد.' : dirty ? 'تغییرات ذخیره نشده‌اند.' : ''}
          </span>
        </div>
        {error && <p className="text-[13.5px] text-[var(--fg-danger)]">{error}</p>}
      </section>

      <Card>
        <CardHeader className="mb-0">
          <CardTitle>ساعت آرام</CardTitle>
          <CardDescription>
            {quiet.start === quiet.end
              ? 'ساعت آرام خاموش است؛ پیامک و پیام‌رسان هر ساعتی ممکن است برسند.'
              : `بین ساعت ${hour(quiet.start)} تا ${hour(quiet.end)} فقط اعلان‌های فوری پیامک و پیام‌رسان می‌شوند. بقیه ساعت ${hour(quiet.end)} صبح می‌رسند — گم نمی‌شوند.`}
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}

function ChannelToggle({
  label,
  checked,
  disabled,
  hint,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  hint?: string;
  onChange: () => void;
}) {
  return (
    <label
      className={
        'inline-flex items-center gap-2 rounded-[var(--radius-full)] border px-3 py-1.5 text-[13.5px] ' +
        (disabled
          ? 'cursor-not-allowed border-[var(--border-subtle)] text-[var(--fg-tertiary)]'
          : checked
            ? 'cursor-pointer border-[var(--brand-600)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
            : 'cursor-pointer border-[var(--border-default)] text-[var(--fg-secondary)] hover:border-[var(--brand-400)]')
      }
    >
      <input
        type="checkbox"
        className="size-4 accent-[var(--brand-600)]"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
      />
      {label}
      {hint && <span className="text-[12px] text-[var(--fg-tertiary)]">({hint})</span>}
    </label>
  );
}

function ChannelCard({
  status,
  token,
  onChange,
  reload,
}: {
  status: ChannelStatus;
  token: string;
  onChange: (prefs: NotificationPreferences) => void;
  reload: () => Promise<NotificationPreferences | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [address, setAddress] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState('');
  const channel = status.channel as LinkableChannel;

  // پیوند تلگرام در خود تلگرام کامل می‌شود؛ این صفحه تا وصل شدن می‌پرسد.
  useEffect(() => {
    if (!waiting) return;
    const started = Date.now();
    const timer = setInterval(() => {
      void reload().then((next) => {
        const linked = next?.channels.find((c) => c.channel === status.channel)?.linked;
        if (linked || Date.now() - started > LINK_POLL_LIMIT_MS) {
          setWaiting(false);
          setMessage(linked ? null : 'پیوند منقضی شد. دوباره امتحان کن.');
        }
      });
    }, LINK_POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, reload, status.channel]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'انجام نشد. دوباره تلاش کن.');
    } finally {
      setBusy(false);
    }
  }

  const connectTelegram = () =>
    run(async () => {
      const link = await startChannelLink(token, 'TELEGRAM');
      if (link.deep_link) window.open(link.deep_link, '_blank', 'noopener,noreferrer');
      setWaiting(true);
    });

  const sendCode = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await startChannelLink(token, channel, address.trim());
      setCodeSent(true);
    });
  };

  const confirm = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      onChange(await confirmChannelLink(token, channel, toLatinDigits(code.trim())));
      setCodeSent(false);
      setCode('');
    });
  };

  const disconnect = () =>
    run(async () => {
      await unlinkChannel(token, channel);
      await reload();
    });

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
          {status.linked ? 'فعال' : status.requires_link ? 'وصل نیست' : 'بدون نشانی'}
        </span>
      </div>

      {status.linked && status.address_masked && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]" dir="ltr">
          {status.address_masked}
        </p>
      )}

      {!status.linked && status.channel === 'EMAIL' && (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          ایمیل فقط به نشانی تأییدشده می‌رود. با ایمیل وارد شو تا تأیید شود.
        </p>
      )}

      {status.requires_link && status.linked && (
        <Button
          variant="ghost"
          size="sm"
          className="self-start"
          onClick={() => void disconnect()}
          loading={busy}
        >
          قطع اتصال
        </Button>
      )}

      {status.channel === 'TELEGRAM' && !status.linked && (
        <>
          <Button
            size="sm"
            className="self-start"
            onClick={() => void connectTelegram()}
            loading={busy}
          >
            اتصال به تلگرام
          </Button>
          {waiting && (
            <p role="status" className="text-[13px] text-[var(--fg-secondary)]">
              در تلگرام دکمهٔ «Start» را بزن. این صفحه خودش به‌روز می‌شود.
            </p>
          )}
        </>
      )}

      {status.channel === 'EITAA' && !status.linked && !codeSent && (
        <form onSubmit={sendCode} className="flex flex-col gap-2">
          <Input
            label="شناسهٔ ایتا"
            forceLtr
            placeholder="@username"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            required
          />
          <Button type="submit" size="sm" className="self-start" loading={busy}>
            فرستادن کد
          </Button>
        </form>
      )}

      {status.channel === 'EITAA' && !status.linked && codeSent && (
        <form onSubmit={confirm} className="flex flex-col gap-2">
          <Input
            label="کدی که در ایتا گرفتی"
            forceLtr
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            required
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={busy}>
              تأیید
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setCodeSent(false)}>
              شناسهٔ دیگر
            </Button>
          </div>
        </form>
      )}

      {message && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {message}
        </p>
      )}
    </Card>
  );
}
