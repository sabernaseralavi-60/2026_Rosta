'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';

import { cn } from '@/lib/cn';

import { SearchIcon } from './SearchIcon';

/**
 * دکمهٔ جستجو و میان‌بر ⌘K — همیشه در پوسته (§3.7، M7-13).
 *
 * خود پالت با import پویا و فقط پس از اولین باز شدن می‌آید (M7-15): دیالوگ
 * Radix و منطق جستجو دیگر در JS اولیهٔ هر صفحهٔ واردشده نیستند. پس از اولین
 * بار، پالت mount می‌ماند تا باز کردن دوباره فوری باشد. بستن دیالوگ فوکوس را
 * به همین دکمه برمی‌گرداند (FocusScope Radix عنصر قبلی را به یاد دارد).
 */
const CommandPalette = dynamic(() => import('./CommandPalette').then((m) => m.CommandPalette), {
  ssr: false,
});

export function CommandPaletteTrigger() {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // ⌘K در مک، Ctrl+K در بقیه — از هر جای پوسته.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setLoaded(true);
        setOpen((value) => !value);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <button
        type="button"
        className={cn(
          'flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)]',
          'bg-[var(--bg-sunken)] px-3 text-[13px] text-[var(--fg-secondary)]',
          'transition-colors hover:border-[var(--border-default)] hover:text-[var(--fg-secondary)]',
        )}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-keyshortcuts="Control+K Meta+K"
        onClick={() => {
          setLoaded(true);
          setOpen(true);
        }}
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
      {loaded && <CommandPalette open={open} onOpenChange={setOpen} />}
    </>
  );
}
