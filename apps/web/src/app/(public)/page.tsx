import type { Metadata } from 'next';
import Link from 'next/link';

import { type PublicStats, serverGet, type Story } from '@/lib/api/public';
import { statTiles } from '@/lib/public/home';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * صفحهٔ اصلی — §3.2، §10.10، M7-10.
 *
 * «در یک نگاه (بدون اسکرول) باید مشخص باشد این سامانه چیست و کاربر چه سودی
 * می‌برد.» بدون تصویر استوک: فقط تایپوگرافی، رنگ و دادهٔ واقعی. آمار از
 * `/public/stats` می‌آید و ساعتی یک بار تازه می‌شود (ISR)؛ اگر API در
 * دسترس نباشد، صفحه بی‌آمار بالا می‌آید، نه با عدد ساختگی.
 */

export const revalidate = 3600;

export const metadata: Metadata = {
  title: { absolute: 'سیلپ — از مصرف‌کنندهٔ دانش، به تولیدکنندهٔ ارزش' },
  description:
    'پلتفرمی برای دانشجویانی که می‌خواهند چیزی بسازند، نه فقط نمره بگیرند: آموزش، پژوهش، کارآفرینی و حل مسائل واقعی شهر.',
};

const PATHS: { title: string; body: string; color: string; href: string }[] = [
  {
    title: 'آموزش',
    body: 'دروس با جزوه، آزمون هفتگی و پروژهٔ واقعی — نمره‌ای که از کار می‌آید، نه از حفظ.',
    color: 'var(--cat-learning)',
    href: '/login',
  },
  {
    title: 'پژوهش',
    body: 'مسیر چهارسطحی از مرور ادبیات تا مقالهٔ Q1، با بانک موضوع و بازبین در هر گام.',
    color: 'var(--cat-research)',
    href: '/research',
  },
  {
    title: 'کارآفرینی',
    body: 'پروژه‌های واقعی با فروش واقعی — از خرمای صابر تا نرم‌افزار کشاورزی — و سهم از درآمد.',
    color: 'var(--cat-startup)',
    href: '/projects',
  },
  {
    title: 'حل مسئله',
    body: 'مسائل واقعی شهرداری: مدل SUMO، سناریو و داشبورد، در گردش‌کار هشت‌مرحله‌ای.',
    color: 'var(--cat-community)',
    href: '/city',
  },
];

const STEPS: { title: string; hint: string }[] = [
  { title: 'بگو چه بلدی و چه داری', hint: 'سه دقیقه — مهارت، امکانات، علاقه' },
  { title: 'پروژه‌های مناسبت را ببین', hint: 'با دلیل: «چون Python قوی داری و خودرو»' },
  { title: 'بساز، تحویل بده، امتیاز بگیر', hint: 'هر مرحلهٔ تأییدشده امتیاز و گواهی دارد' },
];

export default async function HomePage() {
  const [stats, stories] = await Promise.all([
    serverGet<PublicStats>('/public/stats', revalidate),
    serverGet<Story[]>('/public/stories', revalidate),
  ]);
  const tiles = stats.ok ? statTiles(stats.data) : [];
  const realStories = stories.ok ? stories.data : [];

  return (
    <>
      <section
        aria-labelledby="hero-title"
        className="page flex flex-col items-center gap-6 py-14 text-center md:py-20"
      >
        {/* اندازه روی span: قاعدهٔ پایهٔ h1 در globals.css بیرون از لایه‌های
            Tailwind است و کلاس خود h1 را می‌پوشاند. */}
        <h1 id="hero-title">
          <span className="block text-[34px] leading-[1.35] md:text-[48px]">
            از مصرف‌کنندهٔ دانش،
            <br />
            به تولیدکنندهٔ ارزش
          </span>
        </h1>
        <p className="max-w-[52ch] text-[17px] leading-[1.9] text-[var(--fg-secondary)]">
          پلتفرمی برای دانشجویانی که می‌خواهند چیزی بسازند، نه فقط نمره بگیرند: آموزش، پژوهش،
          کارآفرینی و حل مسائل واقعی شهر، در یک جا.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          {/* دکمهٔ اصلی زعفرانی است — تنها عنصر اشباع صفحه (§10.10). */}
          <Link
            href="/login"
            className="inline-flex h-12 items-center rounded-[var(--radius-md)] bg-[var(--accent-500)] px-7 text-[16px] font-semibold text-[var(--neutral-900)] hover:bg-[var(--accent-600)]"
          >
            شروع کن ←
          </Link>
          <Link
            href="/projects"
            className="inline-flex h-12 items-center rounded-[var(--radius-md)] px-6 text-[16px] font-medium text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)] hover:text-[var(--fg-primary)]"
          >
            پروژه‌ها را ببین
          </Link>
        </div>
        {tiles.length > 0 && (
          <dl
            aria-label="آمار زندهٔ سامانه"
            className="mt-4 grid w-full max-w-[720px] grid-cols-2 gap-3 md:grid-cols-4"
          >
            {tiles.map((tile) => (
              <div
                key={tile.label}
                className="flex flex-col-reverse items-center gap-0.5 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-4"
              >
                <dt className="text-[13px] text-[var(--fg-secondary)]">{tile.label}</dt>
                <dd className="text-[26px] font-bold">{tile.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section aria-labelledby="paths-title" className="page flex flex-col gap-6 py-12">
        <h2 id="paths-title" className="text-center">
          چهار مسیر رشد
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PATHS.map((path) => (
            <li key={path.title}>
              <Link
                href={path.href}
                className="flex h-full flex-col gap-2 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 pt-6 transition-shadow hover:shadow-[var(--shadow-md)]"
                style={{ borderTop: `4px solid ${path.color}` }}
              >
                <h3 className="text-[18px]">{path.title}</h3>
                <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">{path.body}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="how-title" className="page flex flex-col items-center gap-6 py-12">
        <h2 id="how-title">چطور کار می‌کند؟</h2>
        <ol className="flex w-full max-w-[640px] flex-col gap-4">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex items-start gap-4">
              <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--brand-600)] text-[15px] font-semibold text-[var(--fg-on-brand)]"
              >
                {toPersianDigits(index + 1)}
              </span>
              <span className="flex flex-col">
                <span className="text-[17px] font-semibold">{step.title}</span>
                <span className="text-[14px] text-[var(--fg-secondary)]">{step.hint}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {realStories.length > 0 && (
        <section aria-labelledby="stories-title" className="page flex flex-col gap-6 py-12">
          <h2 id="stories-title" className="text-center">
            {realStories.length === 3 ? 'سه داستان واقعی' : 'داستان‌های واقعی'}
          </h2>
          <ul className="grid gap-4 md:grid-cols-3">
            {realStories.map((story) => (
              <li key={story.project_id}>
                <article className="flex h-full flex-col gap-2 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
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
                          className="font-medium text-[var(--brand-700)]"
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

      <section className="page flex flex-col items-center gap-4 py-16 text-center">
        <h2>پروژهٔ بعدی تو کدام است؟</h2>
        <p className="max-w-[48ch] text-[15px] text-[var(--fg-secondary)]">
          با شمارهٔ موبایل وارد شو، سه دقیقه به چند پرسش جواب بده و پیشنهادهایت را ببین.
        </p>
        <Link
          href="/login"
          className="inline-flex h-12 items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-7 text-[16px] font-semibold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
        >
          ورود و ثبت‌نام
        </Link>
      </section>
    </>
  );
}
