import type { Metadata } from 'next';
import Link from 'next/link';

import { ContentCard } from '@/components/public/ContentCard';
import { fetchContentList } from '@/lib/api/content';
import { type PublicStats, serverGet, type Story } from '@/lib/api/public';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';
import { statTiles } from '@/lib/public/home';

/**
 * صفحهٔ اصلی — ساده و یادگیری‌محور.
 *
 * پیام اصلی فقط «یاد بگیر و رشد کن» است؛ هیچ وعدهٔ برون‌سپاری به دانشجو داده
 * نمی‌شود و متن‌ها به رشتهٔ خاصی گره نخورده‌اند. مشتری‌های بیرونی (مثلاً از
 * دیوار) با یک پیوند کوچک و کم‌رنگ به «ثبت درخواست» می‌رسند. آمار و مطالب از
 * API می‌آیند؛ اگر نبودند، بخش مربوط دیده نمی‌شود، نه با متن ساختگی.
 */

export const revalidate = 300;

export const metadata: Metadata = {
  title: { absolute: 'رُستا — یاد بگیر و رشد کن' },
  description: 'مطالب آموزشی، آزمون، پروژه و پژوهش؛ جایی برای یادگیری و رشد گام‌به‌گام.',
};

const FEATURES = [
  {
    icon: '📖',
    title: 'مطالب و جزوه',
    body: 'درس‌نامه، خلاصهٔ کتاب و مقاله و مثال‌های حل‌شده؛ هفته‌به‌هفته و قابل‌پیگیری.',
  },
  {
    icon: '✅',
    title: 'آزمون و بازخورد',
    body: 'با آزمون‌های کوتاه بسنج چه یاد گرفته‌ای و نمره و پیشرفتت را یک‌جا ببین.',
  },
  {
    icon: '🌱',
    title: 'پروژه و پژوهش',
    body: 'آنچه یاد گرفته‌ای را در یک پروژه یا کار پژوهشی تیمی به کار ببر و رشد کن.',
  },
] as const;

export default async function HomePage() {
  const [stats, stories, latest] = await Promise.all([
    serverGet<PublicStats>('/public/stats', revalidate),
    serverGet<Story[]>('/public/stories', revalidate),
    fetchContentList({ limit: 4 }, revalidate),
  ]);
  const tiles = stats.ok ? statTiles(stats.data) : [];
  const realStories = stories.ok ? stories.data : [];
  const articles = latest.ok ? latest.data.items : [];

  return (
    <>
      {/* ── قهرمان ─────────────────────────────────────────────────── */}
      <section
        aria-labelledby="hero-title"
        className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]"
      >
        <div className="page flex flex-col items-center gap-6 py-20 text-center md:py-28">
          <h1 id="hero-title">
            {/* اندازه روی span: قاعدهٔ پایهٔ h1 در globals.css بیرون از لایه‌های Tailwind است. */}
            <span className="block text-[36px] font-extrabold leading-[1.4] md:text-[56px]">
              یاد بگیر <span className="text-[var(--fg-brand)]">و رشد کن</span>
            </span>
          </h1>
          <p className="max-w-[48ch] text-[16px] leading-[2] text-[var(--fg-secondary)] md:text-[18px]">
            مطالب آموزشی، آزمون، پروژه و پژوهش؛ گام‌به‌گام و با بازخورد.
          </p>
          <div className="flex flex-wrap justify-center gap-3 pt-2">
            <Link
              href="/login"
              className="h-13 inline-flex items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-8 text-[16px] font-bold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
            >
              شروع کن
            </Link>
            <Link
              href="/content"
              className="h-13 inline-flex items-center rounded-[var(--radius-md)] border border-[var(--border-strong)] px-8 text-[16px] font-semibold hover:bg-[var(--bg-sunken)]"
            >
              مرور مطالب
            </Link>
          </div>
        </div>
      </section>

      {tiles.length > 0 && (
        <section aria-label="آمار زندهٔ سامانه" className="page pt-10">
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--border-subtle)] shadow-[var(--shadow-lg)] md:grid-cols-4">
            {tiles.map((tile) => (
              <div
                key={tile.label}
                className="flex flex-col-reverse items-center gap-0.5 bg-[var(--bg-surface)] px-3 py-5"
              >
                <dt className="text-[13px] text-[var(--fg-secondary)]">{tile.label}</dt>
                <dd className="text-[28px] font-bold text-[var(--fg-brand)]">{tile.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* ── مسیر یادگیری ─────────────────────────────────────────────── */}
      <section aria-labelledby="features-title" className="page flex flex-col gap-8 py-16">
        <h2 id="features-title" className="text-center text-[26px]">
          مسیر یادگیری تو
        </h2>
        <ul className="grid gap-5 md:grid-cols-3">
          {FEATURES.map((item) => (
            <li
              key={item.title}
              className="flex flex-col gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6"
            >
              <span className="text-[28px]" aria-hidden="true">
                {item.icon}
              </span>
              <h3 className="text-[18px]">{item.title}</h3>
              <p className="text-[14.5px] leading-[1.9] text-[var(--fg-secondary)]">{item.body}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* ── تازه‌ترین مطالب ─────────────────────────────────────────── */}
      {articles.length > 0 && (
        <section aria-labelledby="latest-title" className="page flex flex-col gap-6 py-10">
          <div className="flex items-end justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h2 id="latest-title" className="text-[26px]">
                تازه‌ترین مطالب
              </h2>
              <p className="text-[14px] text-[var(--fg-secondary)]">
                مقاله، خلاصهٔ کتاب و مثال — هر روز چیزی تازه.
              </p>
            </div>
            <Link
              href="/content"
              className="shrink-0 text-[14px] font-semibold text-[var(--fg-brand)]"
            >
              همهٔ مطالب ←
            </Link>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            {articles[0] && (
              <div className="lg:col-span-2">
                <ContentCard item={articles[0]} featured />
              </div>
            )}
            {articles.slice(1, 4).map((item, index) => (
              <div key={item.slug} className={index === 0 ? 'lg:row-span-1' : ''}>
                <ContentCard item={item} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── داستان‌های واقعی ─────────────────────────────────────────── */}
      {realStories.length > 0 && (
        <section aria-labelledby="stories-title" className="page flex flex-col gap-6 py-10">
          <h2 id="stories-title" className="text-center text-[26px]">
            {realStories.length === 3 ? 'سه داستان واقعی' : 'داستان‌های واقعی'}
          </h2>
          <ul className="grid gap-4 md:grid-cols-3">
            {realStories.map((story) => (
              <li key={story.project_id}>
                <article className="flex h-full flex-col gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
                  <p className="text-[12.5px] text-[var(--fg-tertiary)]">
                    {story.kind_fa}
                    {story.course_title && ` · ${story.course_title}`}
                    {story.completed_at && ` · ${formatDateLong(story.completed_at)}`}
                  </p>
                  <h3 className="text-[17px]">{story.title_fa}</h3>
                  <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
                    {story.summary}
                  </p>
                  <p className="mt-auto text-[13px] text-[var(--fg-secondary)]">
                    تیم {toPersianDigits(story.team_size)} نفره ·{' '}
                    {toPersianDigits(story.approved_milestones)} مرحلهٔ تأییدشده
                  </p>
                  {story.members.length > 0 && (
                    <p className="flex flex-wrap gap-x-2 text-[13px]">
                      {story.members.map((member) => (
                        <Link
                          key={member.username}
                          href={`/u/${member.username}`}
                          className="font-medium text-[var(--fg-brand)]"
                        >
                          {member.name}
                        </Link>
                      ))}
                    </p>
                  )}
                </article>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── دعوت پایانی ─────────────────────────────────────────────── */}
      <section className="page py-10">
        <div className="flex flex-col items-center gap-4 rounded-[var(--radius-xl)] bg-[var(--brand-50)] px-6 py-14 text-center">
          <h2 className="text-[26px] leading-[1.6]">امروز از یک گام کوچک شروع کن</h2>
          <Link
            href="/login"
            className="h-13 inline-flex items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-8 text-[16px] font-bold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
          >
            ساخت حساب رایگان
          </Link>
        </div>
        {/* مسیر بیرونی: عمداً ریز و کم‌رنگ. */}
        <p className="pt-6 text-center text-[13px] text-[var(--fg-tertiary)]">
          برای اهداف غیرآموزشی،{' '}
          <Link
            href="/intake"
            className="underline underline-offset-4 hover:text-[var(--fg-brand)]"
          >
            ثبت درخواست
          </Link>
        </p>
      </section>
    </>
  );
}
