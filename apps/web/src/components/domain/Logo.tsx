/**
 * نشان برند «رُستا» — رویش (ساقه، دو برگ، ریشه). رنگ‌ها از توکن‌های موجود
 * سایت (`--brand-600/700`, `--accent-500`)، نه رنگ تازه.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={className}>
      <path d="M16 18 C12 19 8 18 7 15 C11 14 16 16 16 18 Z" fill="var(--accent-500)" />
      <path d="M16 17 C10 15 6 11 7 6 C12 8 16 12 16 17 Z" fill="var(--brand-600)" />
      <path d="M16 17 C22 15 26 11 25 6 C20 8 16 12 16 17 Z" fill="var(--brand-600)" />
      <path
        d="M16 17 L16 21 M16 21 C16 24.5 14.3 27 11.5 29 M16 21 C16 24.5 16 27 16 30 M16 21 C16 24.5 17.7 27 20.5 29"
        stroke="var(--brand-700)"
        strokeWidth="1.3"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

export function Logo({ className = '', markClassName = 'size-8' }: { className?: string; markClassName?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark className={markClassName} />
      <span className="text-[var(--fg-brand)]">رُستا</span>
    </span>
  );
}
