'use client';

import Link from 'next/link';
import { type ReactNode, useEffect, useState } from 'react';

import { type ContentDetail, fetchContentAsViewer } from '@/lib/api/content';
import { readSession } from '@/lib/auth/session';
import { resolveContentLink } from '@/lib/markdown/links';

const LOCK_TITLE: Record<string, string> = {
  REGISTERED: 'این مطلب برای کاربران با حساب رایگان است',
  STUDENT: 'این مطلب مخصوص دانشجویان است',
  MEMBER: 'این مطلب مخصوص اعضاست',
  PREMIUM: 'این مطلب در بستهٔ ویژه است',
};

/**
 * متن مطلب.
 *
 * سرور بی‌ورود رندر می‌کند و متن محتوای عمومی را **آماده** (`rendered`) می‌دهد؛ پس
 * KaTeX و مبدل Markdown به بستهٔ مرورگر نمی‌روند. محتوای قفل‌شده فقط عنوان و خلاصه
 * دارد. اگر کاربر واردشده باشد، یک بار با نشست خودش پرسیده می‌شود و فقط در همین
 * مسیر (بارگذاری تنبل) مبدل به مرورگر می‌آید؛ متن هرگز بی‌احراز از سرور بیرون
 * نمی‌آید.
 */
export function ContentBody({
  initial,
  rendered,
}: {
  initial: ContentDetail;
  rendered: ReactNode;
}) {
  const [detail, setDetail] = useState(initial);
  const [unlocked, setUnlocked] = useState<ReactNode>(null);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const session = readSession();
    setSignedIn(session !== null);
    if (!initial.locked || session === null) return;
    let cancelled = false;
    (async () => {
      try {
        const next = await fetchContentAsViewer(initial.slug, session.accessToken);
        if (cancelled) return;
        setDetail(next);
        if (!next.locked && next.body_md) {
          const { render } = await import('@/lib/markdown/render');
          if (!cancelled) setUnlocked(render(next.body_md, resolveContentLink));
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initial.slug, initial.locked]);

  const body = rendered ?? unlocked;
  if (body) {
    return (
      <div className="flex flex-col gap-4 text-[16px] [&_h2]:mt-8 [&_p]:leading-[2.1]">{body}</div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[16px] leading-[2.1] text-[var(--fg-secondary)]">{detail.summary}</p>
      <div className="relative overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
        <div aria-hidden="true" className="text-[30px]">
          🔒
        </div>
        <h2 className="mt-2 text-[20px]">{LOCK_TITLE[detail.access] ?? 'این مطلب قفل است'}</h2>
        <p className="mx-auto mt-2 max-w-[44ch] text-[14px] leading-[2] text-[var(--fg-secondary)]">
          {signedIn === false
            ? detail.access === 'REGISTERED' || detail.access === 'STUDENT'
              ? 'برای خواندن متن کامل وارد شوید یا حساب رایگان بسازید.'
              : 'این بخش با عضویت باز می‌شود؛ عضویت به‌زودی فعال می‌شود.'
            : failed
              ? 'اتصال به سرور برقرار نشد. صفحه را دوباره باز کنید.'
              : signedIn
                ? detail.locked
                  ? 'حساب شما هنوز به این مطلب دسترسی ندارد. عضویت و بستهٔ ویژه به‌زودی فعال می‌شود.'
                  : 'در حال آماده‌سازی متن…'
                : 'در حال بررسی دسترسی…'}
        </p>
        {signedIn === false && (
          <Link
            href="/login"
            className="mt-5 inline-flex h-11 items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-6 text-[15px] font-semibold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
          >
            ورود و ثبت‌نام
          </Link>
        )}
      </div>
    </div>
  );
}
