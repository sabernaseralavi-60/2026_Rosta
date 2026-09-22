'use client';

import { useCallback, useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react';

import { cn } from '@/lib/cn';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

/**
 * ورودی کد یک‌بارمصرف — §3.3.
 *
 * «۶ خانهٔ کد با چسباندن خودکار.»
 *
 * سه نکته که معمولاً فراموش می‌شوند و کاربر را عذاب می‌دهند:
 *
 * ۱. **جهت.** خانه‌ها با `dir="ltr"` چیده می‌شوند. کد عدد است و از چپ
 *    خوانده می‌شود؛ در یک صفحهٔ RTL اگر این را تنظیم نکنیم، رقم اول
 *    سمت راست می‌افتد و کاربر کد را وارونه می‌بیند.
 * ۲. **چسباندن.** کاربر کل کد را از پیامک کپی می‌کند. چسباندن در هر
 *    خانه باید همهٔ خانه‌ها را پر کند، نه فقط یکی را.
 * ۳. **ارقام فارسی.** کیبورد فارسی «۴۸۲۹۱۳» می‌دهد؛ به لاتین تبدیل
 *    می‌شود وگرنه سرور رد می‌کند.
 */

export interface OtpInputProps {
  length?: number;
  value: string;
  onChange: (value: string) => void;
  /** وقتی همهٔ خانه‌ها پر شدند — معمولاً ارسال خودکار فرم. */
  onComplete?: (value: string) => void;
  disabled?: boolean;
  error?: string;
  label: string;
}

export function OtpInput({
  length = 6,
  value,
  onChange,
  onComplete,
  disabled = false,
  error,
  label,
}: OtpInputProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const completedFor = useRef<string | null>(null);

  const digits = Array.from({ length }, (_, i) => value[i] ?? '');

  useEffect(() => {
    // `onComplete` فقط یک‌بار به‌ازای هر کد کامل صدا زده می‌شود، وگرنه
    // هر رندر دوباره، یک ارسال تکراری می‌سازد.
    if (value.length === length && completedFor.current !== value) {
      completedFor.current = value;
      onComplete?.(value);
    }
    if (value.length < length) completedFor.current = null;
  }, [value, length, onComplete]);

  const focusAt = useCallback((index: number) => {
    refs.current[Math.max(0, Math.min(index, refs.current.length - 1))]?.focus();
  }, []);

  function setDigit(index: number, digit: string) {
    const next = digits.slice();
    next[index] = digit;
    onChange(next.join('').slice(0, length));
  }

  function handleInput(index: number, raw: string) {
    const clean = toLatinDigits(raw).replace(/\D/g, '');
    if (!clean) {
      setDigit(index, '');
      return;
    }

    // اگر کاربر چند رقم یک‌جا وارد کرد (مثلاً تکمیل خودکار مرورگر)،
    // از همین خانه به بعد پخش می‌شود.
    if (clean.length > 1) {
      const merged = (value.slice(0, index) + clean).slice(0, length);
      onChange(merged);
      focusAt(merged.length);
      return;
    }

    setDigit(index, clean);
    if (index < length - 1) focusAt(index + 1);
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      // خانهٔ خالی: پاک کردن باید به خانهٔ قبلی برگردد.
      event.preventDefault();
      setDigit(index - 1, '');
      focusAt(index - 1);
      return;
    }
    // فلش‌ها در LTR منطقی‌اند چون خودِ کد LTR است.
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      focusAt(index - 1);
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      focusAt(index + 1);
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();
    const pasted = toLatinDigits(event.clipboardData.getData('text'))
      .replace(/\D/g, '')
      .slice(0, length);
    if (!pasted) return;
    onChange(pasted);
    focusAt(pasted.length);
  }

  const errorId = 'otp-error';

  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="mb-1 text-[13.5px] font-medium text-[var(--fg-primary)]">
        {label}
      </legend>

      <div className="flex justify-center gap-2" dir="ltr">
        {digits.map((digit, index) => (
          <input
            // خانه‌ها ثابت و هم‌تعداد هستند؛ شاخص اینجا کلید پایداری است.
            key={index}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="text"
            inputMode="numeric"
            autoComplete={index === 0 ? 'one-time-code' : 'off'}
            maxLength={length}
            value={digit}
            aria-label={`رقم ${toPersianDigits(index + 1)} از ${toPersianDigits(length)}`}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            onChange={(event) => handleInput(index, event.target.value)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            onPaste={handlePaste}
            onFocus={(event) => event.target.select()}
            className={cn(
              'size-12 rounded-[var(--radius-md)] border text-center',
              'font-mono text-[20px] tabular-nums text-[var(--fg-primary)]',
              'bg-[var(--bg-surface)] transition-colors duration-[var(--dur-instant)]',
              'disabled:opacity-60',
              error
                ? 'border-[var(--danger-600)]'
                : 'border-[var(--border-default)] hover:border-[var(--border-strong)]',
            )}
          />
        ))}
      </div>

      {error && (
        <p
          id={errorId}
          role="alert"
          className="text-center text-[12.5px] text-[var(--danger-600)]"
        >
          {error}
        </p>
      )}
    </fieldset>
  );
}
