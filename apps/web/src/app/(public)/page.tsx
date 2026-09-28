import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';

import { ContentCard } from '@/components/public/ContentCard';
import { fetchContentList } from '@/lib/api/content';
import { type PublicStats, serverGet, type Story } from '@/lib/api/public';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';
import { PHOTOS, type PhotoKey } from '@/lib/photos';
import { statTiles } from '@/lib/public/home';

/**
 * صفحهٔ اصلی — §3.2، §10.10، فایل مشخصات فاز ۰ بند ۵ تا ۷.
 *
 * سه در ورودی: 📚 یادگیری و رشد، 💼 طرح مسئله / نیاز، و (کوچک‌تر، در هدر و زیر
 * قهرمان) 🤝 همکاری با ما. سپس اثبات ارزش پیش از ثبت‌نام: مطالب واقعی، پژوهش و
 * دادهٔ زنده. آمار و مطالب از API می‌آیند و ISR کوتاه دارند؛ اگر API در دسترس
 * نباشد یا محتوایی نباشد، بخش مربوط دیده نمی‌شود، نه با عدد یا متن ساختگی.
 */

export const revalidate = 300;

export const metadata: Metadata = {
  title: { absolute: 'سیلپ — یاد بگیر، مهارت بساز، یا مسئله‌ات را به ما بسپار' },
  description:
    'آموزش، پژوهش، همکاری و توسعهٔ راه‌حل‌های واقعی؛ از ایده تا اجرا. مطالب تخصصی حمل‌ونقل، عمران و داده، مسیر پژوهش تا مقالهٔ Q1 و پروژه‌های واقعی.',
};

const DOORS: {
  photo: PhotoKey;
  icon: string;
  title: string;
  body: string;
  cta: string;
  href: '/content' | '/intake' | '/collaborate';
}[] = [
  {
    photo: 'learn',
    icon: '📚',
    title: 'یادگیری و رشد',
    body: 'مطالب تخصصی، خلاصهٔ کتاب و مقاله، آزمون و مسیر یادگیری؛ برای دانشجوی ترم، دانشجوی آزاد و پژوهشگر.',
    cta: 'شروع یادگیری',
    href: '/content',
  },
  {
    photo: 'solve',
    icon: '💼',
    title: 'طرح مسئله / نیاز',
    body: 'کسب‌وکار، سازمان، شهرداری یا پژوهشگرید؟ مسئله‌تان را بنویسید؛ مسیر حل را پیشنهاد می‌دهیم.',
    cta: 'مسئله‌ات را بنویس',
    href: '/intake',
  },
  {
    photo: 'collab',
    icon: '🤝',
    title: 'همکاری با ما',
    body: 'متخصص، برنامه‌نویس، تحلیلگر داده یا مشاورید؟ در پروژه‌ها و پژوهش‌های واقعی عضو تیم شوید.',
    cta: 'به تیم بپیوند',
    href: '/collaborate',
  },
];

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
        className="relative isolate flex min-h-[560px] items-center overflow-hidden bg-[var(--neutral-900)] md:min-h-[640px]"
      >
        <Image
          src={PHOTOS.hero.src}
          alt=""
          fill
          priority
          sizes="100vw"
          className="-z-20 object-cover"
        />
        {/* گرادیان از سمت متن (راست) تیره‌تر است؛ در موبایل کل تصویر تیره می‌شود. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 bg-gradient-to-l from-black/85 via-black/60 to-black/25 max-md:from-black/80 max-md:via-black/70 max-md:to-black/55"
        />
        <div className="page flex flex-col gap-6 py-16 text-white md:py-24">
          <p className="w-fit rounded-full border border-white/30 bg-white/10 px-4 py-1.5 text-[13px] font-medium backdrop-blur">
            آموزش · پژوهش · همکاری · حل مسئلهٔ واقعی
          </p>
          <h1 id="hero-title" className="max-w-[34ch]">
            {/* اندازه روی span: قاعدهٔ پایهٔ h1 در globals.css بیرون از لایه‌های Tailwind است. */}
            <span className="block text-[34px] font-extrabold leading-[1.45] md:text-[54px] md:leading-[1.4]">
              یاد بگیر، مهارت بساز و خودت انجام بده؛
              <span className="text-[var(--accent-300)]"> یا مسئله‌ات را به ما بسپار.</span>
            </span>
          </h1>
          <p className="max-w-[54ch] text-[16px] leading-[2] text-white/85 md:text-[18px]">
            آموزش، پژوهش، همکاری و توسعهٔ راه‌حل‌های واقعی؛ از ایده تا اجرا.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/content"
              className="h-13 inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--accent-500)] px-7 text-[16px] font-bold text-[var(--neutral-900)] shadow-lg hover:bg-[var(--accent-400)]"
            >
              📚 یادگیری و رشد
            </Link>
            <Link
              href="/intake"
              className="h-13 inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-white/40 bg-white/10 px-7 text-[16px] font-semibold text-white backdrop-blur hover:bg-white/20"
            >
              💼 طرح مسئله / نیاز
            </Link>
          </div>
          <p className="text-[14px] text-white/75">
            متخصص یا پژوهشگرید؟{' '}
            <Link
              href="/collaborate"
              className="font-semibold text-white underline underline-offset-4"
            >
              🤝 با ما همکاری کنید
            </Link>
          </p>
        </div>
      </section>

      {tiles.length > 0 && (
        <section aria-label="آمار زندهٔ سامانه" className="page relative z-10 -mt-8 md:-mt-10">
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

      {/* ── سه در ورودی ─────────────────────────────────────────────── */}
      <section aria-labelledby="doors-title" className="page flex flex-col gap-8 py-16">
        <div className="flex flex-col gap-2 text-center">
          <h2 id="doors-title" className="text-[26px]">
            از کجا شروع می‌کنی؟
          </h2>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            هر کس یک مسیر دارد؛ فقط همان را می‌بینی.
          </p>
        </div>
        <ul className="grid gap-5 md:grid-cols-3">
          {DOORS.map((door) => {
            const photo = PHOTOS[door.photo];
            return (
              <li key={door.title}>
                <Link
                  href={door.href}
                  className="group relative isolate flex h-full min-h-[340px] flex-col justify-end overflow-hidden rounded-[var(--radius-xl)] p-6 text-white"
                >
                  <Image
                    src={photo.src}
                    alt=""
                    fill
                    sizes="(min-width: 768px) 33vw, 100vw"
                    className="-z-20 object-cover transition-transform duration-[var(--dur-slow)] group-hover:scale-[1.05]"
                  />
                  <div
                    aria-hidden="true"
                    className="absolute inset-0 -z-10 bg-gradient-to-t from-black/85 via-black/40 to-black/5"
                  />
                  <span className="text-[30px]" aria-hidden="true">
                    {door.icon}
                  </span>
                  <h3 className="mt-2 text-[22px]">{door.title}</h3>
                  <p className="mt-2 text-[14px] leading-[1.9] text-white/85">{door.body}</p>
                  <span className="mt-4 inline-flex w-fit items-center gap-1 rounded-full bg-white px-4 py-2 text-[14px] font-semibold text-[var(--neutral-900)] group-hover:bg-[var(--accent-300)]">
                    {door.cta} ←
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ── تازه‌ترین مطالب ─────────────────────────────────────────── */}
      {articles.length > 0 && (
        <section aria-labelledby="latest-title" className="page flex flex-col gap-6 py-10">
          <div className="flex items-end justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h2 id="latest-title" className="text-[26px]">
                تازه‌ترین مطالب آموزشی
              </h2>
              <p className="text-[14px] text-[var(--fg-secondary)]">
                مقاله، خلاصهٔ کتاب و مقاله، مثال و مطالعهٔ موردی — هر روز چیزی تازه.
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

      {/* ── پژوهش و داده ─────────────────────────────────────────────── */}
      <section aria-labelledby="research-title" className="page py-12">
        <div className="grid overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] md:grid-cols-2">
          <div className="relative min-h-[280px]">
            <Image
              src={PHOTOS.research.src}
              alt={PHOTOS.research.alt}
              fill
              sizes="(min-width: 768px) 50vw, 100vw"
              className="object-cover"
            />
          </div>
          <div className="flex flex-col justify-center gap-4 p-8 md:p-12">
            <p className="text-[13px] font-semibold text-[var(--fg-research)]">پژوهش و داده</p>
            <h2 id="research-title" className="text-[26px] leading-[1.5]">
              از «می‌خواهم مقاله بنویسم» تا مسئلهٔ پژوهشی روشن
            </h2>
            <p className="text-[15px] leading-[2] text-[var(--fg-secondary)]">
              مجموعه‌داده را انتخاب کن، مسئله را تعریف کن، مقالهٔ مرجع را بخوان و شکاف را پیدا کن.
              هر گام بازبین دارد و مسیر چهارسطحی تا مقالهٔ Q1 ادامه می‌یابد.
            </p>
            <div>
              <Link
                href="/research"
                className="inline-flex h-11 items-center rounded-[var(--radius-md)] border border-[var(--border-strong)] px-5 text-[14px] font-semibold hover:bg-[var(--bg-sunken)]"
              >
                مسیر پژوهش ←
              </Link>
            </div>
          </div>
        </div>
      </section>

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
        <div className="relative isolate overflow-hidden rounded-[var(--radius-xl)] px-6 py-16 text-center text-white md:px-16">
          <Image src={PHOTOS.agri.src} alt="" fill sizes="100vw" className="-z-20 object-cover" />
          <div aria-hidden="true" className="absolute inset-0 -z-10 bg-black/65" />
          <h2 className="mx-auto max-w-[24ch] text-[28px] leading-[1.6] md:text-[34px]">
            امروز از یک گام کوچک شروع کن
          </h2>
          <p className="mx-auto mt-3 max-w-[48ch] text-[15px] leading-[2] text-white/85">
            حساب رایگان بساز و مسیر یادگیری‌ات را ببین، یا مسئله‌ات را در چند دقیقه برای ما بنویس.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href="/login"
              className="h-13 inline-flex items-center rounded-[var(--radius-md)] bg-[var(--accent-500)] px-7 text-[16px] font-bold text-[var(--neutral-900)] hover:bg-[var(--accent-400)]"
            >
              ساخت حساب رایگان
            </Link>
            <Link
              href="/intake"
              className="h-13 inline-flex items-center rounded-[var(--radius-md)] border border-white/40 px-7 text-[16px] font-semibold hover:bg-white/10"
            >
              طرح مسئله / نیاز
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
