'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { requestOtp } from '@/lib/api/auth';
import { ApiError, NetworkError } from '@/lib/api/client';
import { rememberOtpDestination } from '@/lib/auth/pending-otp';
import { toLatinDigits } from '@/lib/format/digits';

/**
 * فرم ورود — §3.3، FR-AUTH-01.
 *
 * الزامات این ناحیه (§3.3):
 *   · حداکثر ۷ فیلد در هر صفحه — اینجا یک فیلد.
 *   · کیبورد موبایل: نوع `tel` برای شماره.
 *
 * شماره پیش از ارسال به لاتین تبدیل می‌شود: کاربر ایرانی با کیبورد
 * فارسی «۰۹۱۲…» می‌نویسد و سرور الگوی لاتین می‌خواهد. سرور هم خودش
 * نرمال می‌کند، ولی تبدیل اینجا خطای اعتبارسنجی زودهنگام را درست نشان
 * می‌دهد.
 */
export function LoginForm() {
  const router = useRouter();
  const [mobile, setMobile] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const normalized = toLatinDigits(mobile).trim();
    if (!normalized) {
      setError('شمارهٔ موبایل را وارد کن.');
      return;
    }

    setSubmitting(true);
    try {
      const result = await requestOtp(normalized, 'SMS');
      // شمارهٔ کامل در query نمی‌رود (NFR-01)؛ فقط نسخهٔ پوشانده.
      rememberOtpDestination(normalized);
      const query = new URLSearchParams({
        challenge: result.challenge_id,
        to: result.masked_destination,
        resend: String(result.resend_after),
      });
      router.push(`/verify?${query.toString()}`);
    } catch (cause) {
      setError(messageFor(cause));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <Input
        label="شمارهٔ موبایل"
        hint="مثال: ۰۹۱۲۱۲۳۴۵۶۷"
        name="mobile"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        autoFocus
        maxLength={16}
        value={mobile}
        onChange={(event) => setMobile(event.target.value)}
        error={error ?? undefined}
        // §10.5 — شمارهٔ تلفن همیشه چپ‌به‌راست
        forceLtr
        placeholder="09121234567"
      />

      <Button type="submit" size="lg" fullWidth loading={submitting} loadingLabel="در حال ارسال کد…">
        ارسال کد ورود
      </Button>

      <p className="text-center text-[12.5px] leading-relaxed text-[var(--fg-tertiary)]">
        با ورود، با قواعد استفاده از سامانه موافقت می‌کنی.
      </p>
    </form>
  );
}

/**
 * پیام خطا مستقیماً از سرور می‌آید و طبق §5.1 فارسی و قابل نمایش است.
 * فقط خطای شبکه را خودمان می‌سازیم، چون سرور اصلاً پاسخی نداده.
 */
function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد. کمی بعد دوباره تلاش کن.';
}
