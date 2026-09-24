import type { Metadata } from 'next';
import Link from 'next/link';

import { GUIDES, readGuide, resolveGuideLink } from '@/lib/help/docs';
import { render } from '@/lib/markdown/render';

export const metadata: Metadata = {
  title: 'راهنما',
  description: 'راهنمای فارسی سیلپ برای دانشجو، استاد، مدیر و کاربر عمومی.',
};

// از docs/user در زمان ساخت؛ در اجرا به فایل دست نمی‌زند (M7-19).
export const dynamic = 'force-static';

/** `/help` — فهرست راهنماها، از `docs/user/README.md`. */
export default function HelpIndexPage() {
  return (
    <div className="page py-10">
      <article className="mx-auto flex max-w-[var(--prose-max)] flex-col gap-4 text-[15.5px]">
        {render(readGuide('README.md'), resolveGuideLink)}
        <section aria-labelledby="guides-heading" className="mt-4 flex flex-col gap-3">
          <h2 id="guides-heading" className="text-[21px] font-semibold">
            همهٔ راهنماها
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {GUIDES.map((guide) => (
              <li key={guide.slug}>
                <Link
                  href={`/help/${guide.slug}` as never}
                  className="flex h-full flex-col gap-1 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 hover:border-[var(--border-default)]"
                >
                  <span className="font-semibold text-[var(--fg-brand)]">{guide.title}</span>
                  <span className="text-[13.5px] text-[var(--fg-secondary)]">{guide.summary}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </article>
    </div>
  );
}
