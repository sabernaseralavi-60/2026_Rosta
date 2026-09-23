'use client';

import { useRouter } from 'next/navigation';
import { type FormEvent, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type VentureDetail,
  type VentureInput,
  createVenture,
  updateVenture,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';

/**
 * فرم کسب‌وکار — ثبت (`/ventures/new`) و ویرایش (در صفحهٔ کسب‌وکار).
 *
 * فقط نام و معرفی یک‌خطی اجباری‌اند. چهار فیلد دیگر (شرح، مسئله، بازار،
 * مدل درآمد) معیار خروج مرحلهٔ «ایده»اند (§7.7)؛ خالی گذاشتنشان مانع ثبت
 * نیست، فقط مانع رفتن به گام بعد است — و صفحهٔ کسب‌وکار همین را می‌گوید.
 */
export function VentureForm({
  initial,
  onSaved,
}: {
  initial?: VentureDetail;
  onSaved?: (venture: VentureDetail) => void;
}) {
  const router = useRouter();
  const { accessToken } = useSession();
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    pitch: initial?.pitch ?? '',
    description: initial?.description ?? '',
    problem: initial?.problem ?? '',
    target_market: initial?.target_market ?? '',
    revenue_model: initial?.revenue_model ?? '',
    current_status: initial?.current_status ?? '',
    looking_for_cofounder: initial?.looking_for_cofounder ?? false,
    needed_roles: (initial?.needed_roles ?? []).join('، '),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const input: VentureInput = {
      name: form.name.trim(),
      pitch: form.pitch.trim(),
      description: form.description.trim() || null,
      problem: form.problem.trim() || null,
      target_market: form.target_market.trim() || null,
      revenue_model: form.revenue_model.trim() || null,
      current_status: form.current_status.trim() || null,
      looking_for_cofounder: form.looking_for_cofounder,
      needed_roles: form.needed_roles
        .split(/[,،]/)
        .map((role) => role.trim())
        .filter(Boolean),
    };
    setBusy(true);
    setError(null);
    try {
      const saved = initial
        ? await updateVenture(accessToken, initial.id, input)
        : await createVenture(accessToken, input);
      if (onSaved) onSaved(saved);
      else router.push(`/ventures/${saved.id}`);
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof NetworkError
          ? cause.message
          : 'ذخیره نشد. دوباره تلاش کن.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      {!initial && (
        <header className="flex flex-col gap-1">
          <h1>ثبت کسب‌وکار</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            با نام و یک جملهٔ معرفی شروع کن؛ بقیه را هر وقت آماده بود کامل کن.
          </p>
        </header>
      )}
      <Input
        label="نام کسب‌وکار"
        required
        minLength={2}
        maxLength={120}
        value={form.name}
        onChange={(event) => set('name', event.target.value)}
      />
      <Textarea
        label="معرفی یک‌خطی"
        hint="چه چیزی به چه کسی می‌فروشی؟"
        required
        minLength={10}
        maxLength={280}
        rows={2}
        value={form.pitch}
        onChange={(event) => set('pitch', event.target.value)}
      />
      <Textarea
        label="مسئله‌ای که حل می‌کند"
        maxLength={2000}
        rows={3}
        value={form.problem}
        onChange={(event) => set('problem', event.target.value)}
      />
      <Textarea
        label="شرح کسب‌وکار"
        maxLength={4000}
        rows={4}
        value={form.description}
        onChange={(event) => set('description', event.target.value)}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Textarea
          label="بازار هدف"
          maxLength={2000}
          rows={3}
          value={form.target_market}
          onChange={(event) => set('target_market', event.target.value)}
        />
        <Textarea
          label="مدل درآمد"
          maxLength={2000}
          rows={3}
          value={form.revenue_model}
          onChange={(event) => set('revenue_model', event.target.value)}
        />
      </div>
      {initial && (
        <Textarea
          label="وضعیت فعلی"
          hint="این روزها چه می‌گذرد؟"
          maxLength={2000}
          rows={2}
          value={form.current_status}
          onChange={(event) => set('current_status', event.target.value)}
        />
      )}
      <label className="flex items-center gap-3 text-[14px]">
        <input
          type="checkbox"
          checked={form.looking_for_cofounder}
          onChange={(event) => set('looking_for_cofounder', event.target.checked)}
          className="size-4 accent-[var(--brand-600)]"
        />
        دنبال هم‌بنیان‌گذار هستیم
      </label>
      <Input
        label="نقش‌های مورد نیاز"
        hint="با ویرگول جدا کن — مثلاً بازاریاب، برنامه‌نویس"
        value={form.needed_roles}
        onChange={(event) => set('needed_roles', event.target.value)}
      />

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <Button type="submit" loading={busy} disabled={!accessToken}>
          {initial ? 'ذخیره' : 'ثبت کسب‌وکار'}
        </Button>
        {!initial && (
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            انصراف
          </Button>
        )}
      </div>
    </form>
  );
}
