'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { loginWithPassword, type LoginResult } from '@/lib/api/auth';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  rosterComplete,
  rosterConfirm,
  rosterLookup,
  type RosterConfirm,
  type RosterLookup,
} from '@/lib/api/roster';
import { routeForOnboarding, saveSession } from '@/lib/auth/session';
import { toLatinDigits } from '@/lib/format/digits';

type Mode = 'join' | 'login';
type Step = 'lookup' | 'confirm' | 'code';

/**
 * ورود دانشجوی درس — ADR-0035.
 *
 * شمارهٔ دانشجویی فقط «پیدا کردن ردیف» است، نه رمز: همکلاسی‌ها آن را می‌دانند. حساب را
 * کدی می‌دهد که به ایمیلِ ثبت‌شده در فهرست می‌رود؛ رمزِ ماندگار را خود دانشجو می‌گذارد.
 */
export function StudentAccess() {
  const [mode, setMode] = useState<Mode>('join');

  return (
    <>
      <div className="flex flex-col gap-2">
        <h1>{mode === 'join' ? 'فعال‌سازی حساب دانشجو' : 'ورود با رمز'}</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          {mode === 'join'
            ? 'اگر نام تو در فهرست یکی از درس‌هاست، با موبایل و شمارهٔ دانشجویی‌ات حسابت را فعال کن.'
            : 'با موبایل و رمزی که هنگام فعال‌سازی گذاشتی وارد شو.'}
        </p>
      </div>

      {mode === 'join' ? <JoinFlow /> : <PasswordLogin />}

      <p className="text-center text-[13.5px] text-[var(--fg-secondary)]">
        {mode === 'join' ? (
          <>
            قبلاً فعال کرده‌ای؟{' '}
            <button type="button" className="underline" onClick={() => setMode('login')}>
              ورود با رمز
            </button>
          </>
        ) : (
          <>
            هنوز فعال نکرده‌ای؟{' '}
            <button type="button" className="underline" onClick={() => setMode('join')}>
              فعال‌سازی حساب
            </button>
          </>
        )}
      </p>
      <p className="text-center text-[13px] text-[var(--fg-tertiary)]">
        دانشجوی درس نیستی؟{' '}
        <Link href="/login" className="underline">
          ورود با کد پیامکی
        </Link>
      </p>
    </>
  );
}

function useFinishLogin() {
  const router = useRouter();
  return (result: LoginResult) => {
    saveSession({
      accessToken: result.access_token,
      refreshToken: result.refresh_token,
      user: result.user,
    });
    router.replace(routeForOnboarding(result.user.onboarding_state));
  };
}

function PasswordLogin() {
  const finish = useFinishLogin();
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      finish(await loginWithPassword(toLatinDigits(mobile).trim(), password));
    } catch (cause) {
      setError(messageFor(cause));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      <Input
        label="شمارهٔ موبایل"
        name="mobile"
        type="tel"
        inputMode="tel"
        autoComplete="username"
        autoFocus
        forceLtr
        maxLength={16}
        value={mobile}
        onChange={(event) => setMobile(event.target.value)}
        placeholder="09121234567"
      />
      <Input
        label="رمز عبور"
        name="password"
        type="password"
        autoComplete="current-password"
        forceLtr
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={error ?? undefined}
      />
      <Button type="submit" size="lg" fullWidth loading={busy} loadingLabel="در حال ورود…">
        ورود
      </Button>
    </form>
  );
}

function JoinFlow() {
  const finish = useFinishLogin();
  const [step, setStep] = useState<Step>('lookup');
  const [mobile, setMobile] = useState('');
  const [studentNo, setStudentNo] = useState('');
  const [found, setFound] = useState<RosterLookup | null>(null);
  const [sent, setSent] = useState<RosterConfirm | null>(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setStep('lookup');
    setFound(null);
    setSent(null);
    setCode('');
    setPassword('');
    setError(null);
  }

  if (step === 'lookup') {
    return (
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => {
            setFound(await rosterLookup(toLatinDigits(mobile).trim(), toLatinDigits(studentNo)));
            setStep('confirm');
          });
        }}
      >
        <Input
          label="شمارهٔ موبایل"
          hint="همین شماره نام‌کاربری تو می‌شود."
          name="mobile"
          type="tel"
          inputMode="tel"
          autoComplete="username"
          autoFocus
          forceLtr
          maxLength={16}
          value={mobile}
          onChange={(event) => setMobile(event.target.value)}
          placeholder="09121234567"
        />
        <Input
          label="شمارهٔ دانشجویی"
          hint="برای پیدا کردن نامت در فهرست است؛ رمز تو نیست."
          name="student_no"
          inputMode="numeric"
          autoComplete="off"
          forceLtr
          maxLength={20}
          value={studentNo}
          onChange={(event) => setStudentNo(event.target.value)}
          error={error ?? undefined}
        />
        <Button type="submit" size="lg" fullWidth loading={busy} loadingLabel="در حال جست‌وجو…">
          ادامه
        </Button>
      </form>
    );
  }

  if (step === 'confirm' && found) {
    return (
      <div className="flex flex-col gap-5">
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] px-5 py-4 text-[16px] leading-[2]">
          شما <b>{found.display_name}</b> هستید؟
        </p>
        {!found.has_email && (
          <p role="alert" className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
            برای شما ایمیلی در فهرست ثبت نشده. به استاد بگو ایمیلت را به فهرست اضافه کند، بعد دوباره
            بیا.
          </p>
        )}
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div className="flex gap-3">
          <Button
            size="lg"
            fullWidth
            disabled={!found.has_email}
            loading={busy}
            loadingLabel="در حال ارسال کد…"
            onClick={() =>
              void run(async () => {
                setSent(await rosterConfirm(found.claim_id, true));
                setStep('code');
              })
            }
          >
            بله، من هستم
          </Button>
          <Button
            size="lg"
            variant="secondary"
            fullWidth
            onClick={() => {
              void rosterConfirm(found.claim_id, false).catch(() => undefined);
              reset();
            }}
          >
            نه
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        if (!found) return;
        void run(async () => {
          finish(await rosterComplete(found.claim_id, toLatinDigits(code).trim(), password));
        });
      }}
    >
      <p className="text-[14.5px] leading-[1.9] text-[var(--fg-secondary)]">
        کدی به ایمیل ثبت‌شده در فهرست فرستادیم: <b dir="ltr">{sent?.masked_email ?? ''}</b>
      </p>
      <Input
        label="کد ایمیل"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        autoFocus
        forceLtr
        maxLength={10}
        value={code}
        onChange={(event) => setCode(event.target.value)}
      />
      <Input
        label="رمز تازه"
        hint="حداقل ۸ نویسه. شمارهٔ دانشجویی یا موبایل نباشد."
        name="new_password"
        type="password"
        autoComplete="new-password"
        forceLtr
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={error ?? undefined}
      />
      <Button type="submit" size="lg" fullWidth loading={busy} loadingLabel="در حال فعال‌سازی…">
        فعال‌سازی و ورود
      </Button>
      <button type="button" className="text-[13px] underline" onClick={reset}>
        از اول شروع کن
      </button>
    </form>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد. کمی بعد دوباره تلاش کن.';
}
