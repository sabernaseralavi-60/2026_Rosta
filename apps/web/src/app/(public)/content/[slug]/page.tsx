import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ContentBody } from '@/components/public/ContentBody';
import { ContentCard } from '@/components/public/ContentCard';
import { CoverImage } from '@/components/public/CoverImage';
import { fetchContentDetail } from '@/lib/api/content';
import { formatDateLong } from '@/lib/format/date';
import { resolveContentLink } from '@/lib/markdown/links';
import { render } from '@/lib/markdown/render';
import 'katex/dist/katex.min.css';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * صفحهٔ یک مطلب — فایل مشخصات فاز ۰، بند ۷ و ۲۵.
 *
 * سرور بی‌ورود رندر می‌کند و متن محتوای قفل‌شده را هرگز نمی‌گیرد؛ `ContentBody`
 * برای کاربر واردشده در مرورگر دوباره می‌پرسد. `noindex` برای محتوای غیرعمومی،
 * تا خلاصهٔ قفل‌شده هم در موتور جست‌وجو نشت نکند.
 */

export const revalidate = 60;

type Params = { slug: string };

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { slug } = await params;
  const result = await fetchContentDetail(decodeURIComponent(slug));
  if (!result.ok) return { title: 'مطلب پیدا نشد' };
  const item = result.data;
  return {
    title: item.title_fa,
    description: item.summary,
    robots: item.access === 'PUBLIC' ? undefined : { index: false, follow: true },
    openGraph: { title: item.title_fa, description: item.summary, type: 'article' },
  };
}

export default async function ContentPage({ params }: { params: Promise<Params> }) {
  const { slug } = await params;
  const result = await fetchContentDetail(decodeURIComponent(slug));
  if (!result.ok) notFound();
  const item = result.data;

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: item.title_fa,
    description: item.summary,
    inLanguage: 'fa',
    datePublished: item.published_at ?? undefined,
    keywords: item.topics.join('، ') || undefined,
    isAccessibleForFree: item.access === 'PUBLIC',
  };

  return (
    <article>
      <header className="relative isolate flex min-h-[340px] items-end overflow-hidden bg-[var(--neutral-900)] md:min-h-[420px]">
        <CoverImage cover={item.cover} kind={item.kind} sizes="100vw" priority className="-z-20" />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 bg-gradient-to-t from-black/85 via-black/50 to-black/20"
        />
        <div className="page flex flex-col gap-4 pb-10 pt-24 text-white">
          <nav aria-label="مسیر" className="text-[13px] text-white/75">
            <Link href="/content" className="hover:text-white">
              مطالب
            </Link>
            <span aria-hidden="true"> / </span>
            <span>{item.kind_fa}</span>
          </nav>
          <h1 className="max-w-[26ch]">
            <span className="block text-[30px] font-extrabold leading-[1.5] md:text-[44px]">
              {item.title_fa}
            </span>
          </h1>
          <p className="text-[14px] text-white/80">
            {item.kind_fa} · {toPersianDigits(item.reading_minutes)} دقیقه مطالعه
            {item.published_at && ` · ${formatDateLong(item.published_at)}`}
            {item.access !== 'PUBLIC' && ` · ${item.access_fa}`}
          </p>
        </div>
      </header>

      <div className="page py-10">
        <div className="mx-auto flex max-w-[var(--prose-max)] flex-col gap-8">
          <ContentBody
            initial={item}
            rendered={
              !item.locked && item.body_md ? render(item.body_md, resolveContentLink) : null
            }
          />

          {(item.topics.length > 0 || item.skills.length > 0) && (
            <footer className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-6">
              {item.topics.length > 0 && (
                <p className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="text-[var(--fg-tertiary)]">موضوع‌ها:</span>
                  {item.topics.map((topic) => (
                    <Link
                      key={topic}
                      href={`/content?topic=${encodeURIComponent(topic)}`}
                      className="rounded-full bg-[var(--bg-sunken)] px-3 py-1 text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
                    >
                      {topic}
                    </Link>
                  ))}
                </p>
              )}
              {item.skills.length > 0 && (
                <p className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="text-[var(--fg-tertiary)]">مهارت‌ها:</span>
                  {item.skills.map((skill) => (
                    <span
                      key={skill}
                      className="rounded-full bg-[var(--brand-50)] px-3 py-1 text-[var(--fg-brand)]"
                    >
                      {skill}
                    </span>
                  ))}
                </p>
              )}
            </footer>
          )}
        </div>

        {item.related.length > 0 && (
          <section aria-labelledby="related-title" className="mt-14 flex flex-col gap-5">
            <h2 id="related-title" className="text-[22px]">
              مطالب مرتبط
            </h2>
            <ul className="grid gap-5 md:grid-cols-3">
              {item.related.map((related) => (
                <li key={related.slug}>
                  <ContentCard item={related} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {item.access === 'PUBLIC' && (
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger -- JSON-LD از دادهٔ خودمان، نه ورودی کاربر
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }}
        />
      )}
    </article>
  );
}
