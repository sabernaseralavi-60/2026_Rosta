'use client';

import { type SyntheticEvent, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { type InstructorCandidate, searchInstructors } from '@/lib/api/course-admin';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * گزینش استاد برای ارائه — ADR-0020.
 *
 * مدیر آموزشی فهرست کاربران را نمی‌بیند (`user.view_all` ندارد)؛ فقط کسی را
 * که با نام، نام کاربری یا بخشی از موبایل دنبالش است. موبایل برایش پوشانده
 * است. استاد باید یک بار وارد سامانه شده باشد تا حساب داشته باشد.
 */
export function InstructorPicker({
  token,
  label = 'استاد',
  selected,
  onSelect,
}: {
  token: string;
  label?: string;
  selected: InstructorCandidate | null;
  onSelect: (candidate: InstructorCandidate | null) => void;
}) {
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<InstructorCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(event: SyntheticEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setFound(await searchInstructors(token, query.trim()));
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  if (selected) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-[13.5px] font-medium">{label}</span>
        <p className="flex flex-wrap items-center gap-2 text-[14px]">
          <strong>{selected.name ?? selected.username ?? 'بی‌نام'}</strong>
          {selected.mobile && (
            <span dir="ltr" className="font-mono text-[12.5px] text-[var(--fg-tertiary)]">
              {selected.mobile}
            </span>
          )}
          <Button type="button" size="sm" variant="ghost" onClick={() => onSelect(null)}>
            تغییر
          </Button>
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* فرم تو در تو در HTML مجاز نیست؛ جستجو با Enter همین کادر اجرا می‌شود. */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[14rem] flex-1">
          <Input
            label={`${label} — جستجو با نام، نام کاربری یا موبایل`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              // Enter اینجا فرم بیرونی (ساخت ارائه) را نفرستد.
              if (event.key !== 'Enter') return;
              event.preventDefault();
              if (query.trim().length >= 2) void search(event);
            }}
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          loading={busy}
          disabled={query.trim().length < 2}
          onClick={(event) => void search(event)}
        >
          جستجو
        </Button>
      </div>
      {found && (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-md)] border border-[var(--border-subtle)]">
          {found.length === 0 && (
            <li className="px-3 py-2 text-[13.5px] text-[var(--fg-secondary)]">
              کسی پیدا نشد. استاد باید یک بار با موبایلش وارد سامانه شده باشد.
            </li>
          )}
          {found.map((candidate) => (
            <li key={candidate.id}>
              <button
                type="button"
                onClick={() => onSelect(candidate)}
                className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-start text-[13.5px] hover:bg-[var(--bg-sunken)]"
              >
                <span>
                  {candidate.name ?? candidate.username ?? 'بی‌نام'}
                  {candidate.active_offerings > 0 && (
                    <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                      {' '}
                      · {toPersianDigits(candidate.active_offerings)} ارائهٔ جاری
                    </span>
                  )}
                </span>
                <span dir="ltr" className="font-mono text-[12.5px] text-[var(--fg-tertiary)]">
                  {candidate.mobile}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </div>
  );
}
