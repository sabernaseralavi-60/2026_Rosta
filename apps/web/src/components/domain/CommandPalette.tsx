'use client';

import * as Dialog from '@radix-ui/react-dialog';
import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Command,
  matchCommands,
  MIN_QUERY_LENGTH,
  type SearchGroup,
  searchAll,
} from '@/lib/api/search';
import { readSession } from '@/lib/auth/session';
import { cn } from '@/lib/cn';

/**
 * جستجوی سراسری ⌘K — §3.7، M7-13.
 *
 * الگوی «combobox + listbox» از WAI-ARIA: فوکوس همیشه در ورودی می‌ماند و
 * گزینهٔ فعال با `aria-activedescendant` اعلام می‌شود، پس صفحه‌خوان هر
 * جابه‌جایی با پیکان را می‌خواند (§10.8). دستورات فوراً از حافظه می‌آیند و
 * نتیجه‌های سرور ۲۰۰ میلی‌ثانیه پس از آخرین کلید؛ درخواست کهنه لغو می‌شود
 * تا پاسخ دیررس «کیم» روی نتیجهٔ «کیمیا» ننشیند.
 */

const DEBOUNCE_MS = 200;

interface Option {
  key: string;
  label: string;
  hint: string | null;
  href: string;
  group: string;
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [groups, setGroups] = useState<SearchGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [roles, setRoles] = useState<string[]>([]);
  const listId = useId();
  const listRef = useRef<HTMLDivElement>(null);

  // ⌘K در مک، Ctrl+K در بقیه — از هر جای پوسته.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    setRoles(readSession()?.user.roles ?? []);
  }, [open]);

  useEffect(() => {
    const trimmed = q.trim();
    setError(null);
    if (!open || trimmed.length < MIN_QUERY_LENGTH) {
      setGroups([]);
      setLoading(false);
      return;
    }
    const token = readSession()?.accessToken;
    if (!token) return;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchAll(trimmed, token, controller.signal)
        .then((result) => setGroups(result.groups))
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          setError(
            cause instanceof ApiError || cause instanceof NetworkError
              ? cause.message
              : 'جستجو انجام نشد.',
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [q, open]);

  const commands: Command[] = useMemo(() => matchCommands(q, roles), [q, roles]);

  const options: Option[] = useMemo(
    () => [
      ...commands.map((command) => ({
        key: `cmd-${command.id}`,
        label: command.label,
        hint: null,
        href: command.href,
        group: 'دستورات',
      })),
      ...groups.flatMap((group) =>
        group.items.map((hit) => ({
          key: `${group.kind}-${hit.id}`,
          label: hit.title,
          hint: hit.subtitle,
          href: hit.href,
          group: group.title_fa,
        })),
      ),
    ],
    [commands, groups],
  );

  useEffect(() => setActive(0), [q, groups.length]);

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    node?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const go = useCallback(
    (option: Option | undefined) => {
      if (!option) return;
      setOpen(false);
      setQ('');
      router.push(option.href as Route);
    },
    [router],
  );

  function onInputKey(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((index) => (options.length ? (index + 1) % options.length : 0));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => (options.length ? (index - 1 + options.length) % options.length : 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      go(options[active]);
    }
  }

  const activeId = options[active] ? `${listId}-${active}` : undefined;
  let lastGroup = '';

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        if (!value) setQ('');
      }}
    >
      <Dialog.Trigger asChild>
        <button
          type="button"
          className={cn(
            'flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)]',
            'bg-[var(--bg-sunken)] px-3 text-[13px] text-[var(--fg-secondary)]',
            'transition-colors hover:border-[var(--border-default)] hover:text-[var(--fg-secondary)]',
          )}
          aria-keyshortcuts="Control+K Meta+K"
        >
          <SearchIcon />
          <span className="whitespace-nowrap max-lg:sr-only">جستجو…</span>
          <kbd
            dir="ltr"
            className="hidden whitespace-nowrap rounded border border-[var(--border-subtle)] px-1.5 font-sans text-[11px] 2xl:inline"
          >
            Ctrl K
          </kbd>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content
          className={cn(
            'fixed inset-x-4 top-[12vh] z-50 mx-auto flex max-h-[70vh] max-w-[640px] flex-col',
            'overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)]',
            'bg-[var(--bg-raised)] shadow-[var(--shadow-lg)]',
          )}
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">جستجوی سراسری</Dialog.Title>
          <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4">
            <SearchIcon />
            <input
              autoFocus
              role="combobox"
              aria-expanded={options.length > 0}
              aria-controls={listId}
              aria-activedescendant={activeId}
              aria-autocomplete="list"
              aria-label="جستجو در دروس، پروژه‌ها، ایده‌ها، افراد، منابع و دستورات"
              placeholder="دنبال چه می‌گردی؟ درس، پروژه، ایده، فرد… یا یک دستور"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              onKeyDown={onInputKey}
              className="h-13 flex-1 bg-transparent text-[15px] outline-none placeholder:text-[var(--fg-tertiary)]"
            />
            {loading && (
              <span className="text-[12px] text-[var(--fg-tertiary)]" aria-live="polite">
                در حال جستجو…
              </span>
            )}
          </div>

          <div
            ref={listRef}
            id={listId}
            role="listbox"
            aria-label="نتیجه‌ها"
            className="overflow-y-auto p-2"
          >
            {options.map((option, index) => {
              const heading = option.group !== lastGroup ? option.group : null;
              lastGroup = option.group;
              return (
                <div key={option.key}>
                  {heading && (
                    <div
                      role="presentation"
                      className="px-3 pb-1 pt-3 text-[12px] font-semibold text-[var(--fg-tertiary)]"
                    >
                      {heading}
                    </div>
                  )}
                  <div
                    id={`${listId}-${index}`}
                    data-index={index}
                    role="option"
                    aria-selected={index === active}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(option)}
                    className={cn(
                      'flex cursor-pointer items-baseline justify-between gap-3 rounded-[var(--radius-sm)] px-3 py-2',
                      index === active
                        ? 'bg-[var(--brand-50)] text-[var(--brand-700)]'
                        : 'text-[var(--fg-primary)]',
                    )}
                  >
                    <span className="truncate text-[14px]">{option.label}</span>
                    {option.hint && (
                      <span className="shrink-0 truncate text-[12px] text-[var(--fg-tertiary)] max-sm:hidden">
                        {option.hint}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
            {!loading && q.trim().length >= MIN_QUERY_LENGTH && options.length === 0 && !error && (
              <p className="px-3 py-6 text-center text-[13.5px] text-[var(--fg-secondary)]">
                چیزی با «{q.trim()}» پیدا نشد. واژهٔ کوتاه‌تر یا دیگری را امتحان کن.
              </p>
            )}
            {error && (
              <p role="alert" className="px-3 py-4 text-[13.5px] text-[var(--danger-600)]">
                {error}
              </p>
            )}
          </div>
          <p className="border-t border-[var(--border-subtle)] px-4 py-2 text-[12px] text-[var(--fg-tertiary)]">
            ↑↓ جابه‌جایی · Enter رفتن · Esc بستن
          </p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
