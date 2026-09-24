'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { PublicProfileBody } from '@/components/public/PublicProfileBody';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { fetchMe, type Me, updateProfile } from '@/lib/api/profile';
import {
  fetchPublicProfile,
  PROFILE_SECTIONS,
  type ProfileSection,
  type PublicProfile,
} from '@/lib/api/public';
import { useSession } from '@/lib/auth/use-session';

/**
 * `/me/public-profile` — FR-PROF-03.
 *
 * یک کلید اصلی («نیمرخم عمومی باشد») و یک کلید برای هر بخش. پیش‌نمایش
 * زیر همان چیزی است که دیگران در `/u/…` می‌بینند — صاحب نیمرخ حتی وقتی
 * خصوصی است آن را می‌بیند. موبایل، ایمیل، نمره و رتبهٔ کلاس هیچ‌وقت
 * نمایش داده نمی‌شوند و کلیدی هم برایشان نیست.
 */
export function PublicProfileSettingsView() {
  const { accessToken } = useSession();
  const [me, setMe] = useState<Me | null>(null);
  const [preview, setPreview] = useState<PublicProfile | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshPreview = useCallback(
    async (username: string | null) => {
      if (!accessToken || !username) return;
      try {
        setPreview(await fetchPublicProfile(username, accessToken));
      } catch {
        setPreview(null);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    if (!accessToken) return;
    fetchMe(accessToken)
      .then((result) => {
        setMe(result);
        void refreshPreview(result.username);
      })
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, refreshPreview]);

  async function save(key: string, patch: Parameters<typeof updateProfile>[0]) {
    if (!accessToken || !me) return;
    setSaving(key);
    setError(null);
    try {
      const profile = await updateProfile(patch, accessToken);
      setMe({ ...me, profile });
      await refreshPreview(me.username);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setSaving(null);
    }
  }

  if (!me) {
    return error ? (
      <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
        {error}
      </p>
    ) : (
      <SkeletonCard label="در حال بارگذاری نیمرخ" />
    );
  }
  if (!me.profile || !me.username) {
    return (
      <Card className="flex flex-col gap-3">
        <CardTitle>اول نیمرخت را کامل کن</CardTitle>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          نیمرخ عمومی نام و نام کاربری می‌خواهد که با تکمیل اطلاعات پایه ساخته می‌شود.
        </p>
        <Button asChild>
          <Link href="/onboarding/basic">تکمیل اطلاعات پایه</Link>
        </Button>
      </Card>
    );
  }

  const profile = me.profile;
  const url = `/u/${me.username}`;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>نیمرخ عمومی من</h1>
        <p className="max-w-[65ch] text-[14px] text-[var(--fg-secondary)]">
          صفحه‌ای قابل اشتراک از دستاوردهایت. موبایل، ایمیل، کد ملی، نمرات درسی و رتبه در کلاس هرگز
          در آن نمی‌آیند.
        </p>
      </header>

      <Card className="flex flex-col gap-4">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1.5 size-4"
            checked={profile.is_public}
            disabled={saving !== null}
            onChange={(event) => void save('is_public', { is_public: event.target.checked })}
          />
          <span className="flex flex-col">
            <span className="font-semibold">نیمرخم عمومی باشد</span>
            <span className="text-[13px] text-[var(--fg-secondary)]">
              {profile.is_public ? (
                <>
                  هر کسی با پیوند{' '}
                  <Link href={url} className="font-medium text-[var(--fg-brand)]" dir="ltr">
                    {url}
                  </Link>{' '}
                  آن را می‌بیند و در جستجوی هم‌تیمی پیدایت می‌کنند.
                </>
              ) : (
                'خاموش است: جز خودت کسی این صفحه را نمی‌بیند و در جستجو نمی‌آیی.'
              )}
            </span>
          </span>
        </label>

        <fieldset
          className="flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-4"
          disabled={!profile.is_public}
        >
          <legend className="mb-2 text-[14px] font-semibold">چه چیزهایی دیده شود؟</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {PROFILE_SECTIONS.map((section) => (
              <SectionToggle
                key={section.key}
                label={section.label}
                checked={profile.privacy?.[section.key] ?? true}
                busy={saving === section.key}
                onChange={(value) =>
                  void save(section.key, {
                    privacy: { [section.key]: value } as Partial<Record<ProfileSection, boolean>>,
                  })
                }
              />
            ))}
          </div>
        </fieldset>
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </Card>

      <section aria-labelledby="preview-title" className="flex flex-col gap-3">
        <h2 id="preview-title" className="text-[18px]">
          پیش‌نمایش — آنچه دیگران می‌بینند
        </h2>
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] p-5">
          {preview ? (
            <PublicProfileBody profile={preview} />
          ) : (
            <SkeletonCard label="در حال ساختن پیش‌نمایش" />
          )}
        </div>
      </section>
    </div>
  );
}

function SectionToggle({
  label,
  checked,
  busy,
  onChange,
}: {
  label: string;
  checked: boolean;
  busy: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[14px]">
      <input
        type="checkbox"
        className="size-4"
        checked={checked}
        disabled={busy}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
      {busy && <span className="text-[12px] text-[var(--fg-tertiary)]">در حال ذخیره…</span>}
    </label>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'ذخیره نشد. کمی بعد دوباره تلاش کن.';
}
