'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { OtpInput } from '@/components/ui/OtpInput';
import { requestOtp, verifyOtp } from '@/lib/api/auth';
import { ApiError, NetworkError } from '@/lib/api/client';
import { forgetOtpDestination, readOtpDestination } from '@/lib/auth/pending-otp';
import { routeForOnboarding, saveSession } from '@/lib/auth/session';
import { toPersianDigits } from '@/lib/format/digits';

const CODE_LENGTH = 6;

/**
 * فرم تأیید کد — §3.3، FR-AUTH-01.
 *
 * «۶ خانهٔ کد با چسباندن خودکار، شمارندهٔ معکوس، ارسال مجدد.»
 *
 * کدی که کامل شد بی‌درنگ ارسال می‌شود؛ دکمهٔ «تأیید» برای کسی می‌ماند
 * که کد را اصلاح کرده و ارسال خودکار قبلاً مصرف شده است.
 */
export function VerifyForm() {
  const router = useRouter();
  const params = useSearchParams();

  const challengeId = params.get('challenge') ?? '';
  const resendAfter = Number(params.get('resend') ?? 60);

  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(resendAfter);
  const [activeChallenge, setActiveChallenge] = useState(challengeId);

  // شمارندهٔ معکوس تا امکان ارسال مجدد.
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [secondsLeft]);

  const submit = useCallback(
    async (value: string) => {
      if (!activeChallenge) {
        setError('این صفحه بدون درخواست کد باز شده است. از ابتدا شروع کن.');
        return;
      }
      setError(null);
      setSubmitting(true);
      try {
        const result = await verifyOtp(activeChallenge, value);
        saveSession({
          accessToken: result.access_token,
          refreshToken: result.refresh_token,
          user: result.user,
        });
        forgetOtpDestination();
        router.replace(routeForOnboarding(result.user.onboarding_state));
      } catch (cause) {
        // کد اشتباه پاک می‌شود تا کاربر مجبور به حذف دستی شش رقم نباشد.
        setCode('');
        setError(messageFor(cause));
        setSubmitting(false);
      }
    },
    [activeChallenge, router],
  );

  async function handleResend() {
    if (secondsLeft > 0) return;

    // شمارهٔ کامل فقط در sessionStorage است. اگر نبود (تب تازه، یا
    // ورود مستقیم به این آدرس) کاربر باید از گام اول شروع کند.
    const destination = readOtpDestination();
    if (!destination) {
      router.push('/login');
      return;
    }

    setResending(true);
    setError(null);
    try {
      const result = await requestOtp(destination, 'SMS');
      setActiveChallenge(result.challenge_id);
      setSecondsLeft(result.resend_after);
      setCode('');
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <OtpInput
        label="کد شش‌رقمی"
        length={CODE_LENGTH}
        value={code}
        onChange={setCode}
        onComplete={submit}
        disabled={submitting}
        error={error ?? undefined}
      />

      <Button
        type="button"
        size="lg"
        fullWidth
        loading={submitting}
        loadingLabel="در حال بررسی کد…"
        disabled={code.length < CODE_LENGTH}
        onClick={() => submit(code)}
      >
        تأیید و ورود
      </Button>

      <div className="flex flex-col items-center gap-2 text-[13.5px]">
        {secondsLeft > 0 ? (
          <p className="text-[var(--fg-tertiary)]" aria-live="polite">
            ارسال دوبارهٔ کد تا {toPersianDigits(secondsLeft)} ثانیهٔ دیگر
          </p>
        ) : (
          <Button variant="ghost" size="sm" loading={resending} onClick={handleResend}>
            ارسال دوبارهٔ کد
          </Button>
        )}

        <Button variant="ghost" size="sm" asChild>
          <a href="/login">تغییر شمارهٔ موبایل</a>
        </Button>
      </div>
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد. کمی بعد دوباره تلاش کن.';
}
