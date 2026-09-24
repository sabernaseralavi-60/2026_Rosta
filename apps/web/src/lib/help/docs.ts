import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * راهنمای کاربری — M7-19.
 *
 * منبع یکی است: `docs/user/*.md` در ریشهٔ مخزن، همان که در GitHub خوانده
 * می‌شود. صفحه‌های `/help` در زمان ساخت از همین فایل‌ها ساخته می‌شوند
 * (`generateStaticParams`)، پس در زمان اجرا به فایل نیازی نیست.
 */

export interface Guide {
  slug: string;
  file: string;
  title: string;
  summary: string;
}

export const GUIDES: readonly Guide[] = [
  {
    slug: 'student',
    file: 'student.md',
    title: 'راهنمای دانشجو',
    summary: 'ورود، نیمرخ، پروژه، درس و آزمون، پژوهش، امتیاز و گواهی',
  },
  {
    slug: 'public-learner',
    file: 'public-learner.md',
    title: 'راهنمای کاربر عمومی',
    summary: 'یادگیری بدون شمارهٔ دانشجویی، کتابخانه و اشتراک',
  },
  {
    slug: 'instructor',
    file: 'instructor.md',
    title: 'راهنمای استاد و منتور',
    summary: 'پروژه، بررسی تحویل، پژوهش، کارآفرینی و درس',
  },
  {
    slug: 'admin',
    file: 'admin.md',
    title: 'راهنمای مدیر',
    summary: 'کاربران و نقش‌ها، لاگ حسابرسی، امتیاز، پیام و گواهی',
  },
  {
    slug: 'faq',
    file: 'faq.md',
    title: 'پرسش‌های پرتکرار',
    summary: 'کد ورود، قطع اینترنت در آزمون، امتیاز، گواهی و حریم خصوصی',
  },
];

function docsDir(): string {
  // `next build` و vitest هر دو از apps/web اجرا می‌شوند؛ ریشهٔ مخزن دو پله بالاتر است.
  for (const candidate of [
    join(process.cwd(), 'docs/user'),
    join(process.cwd(), '../../docs/user'),
  ]) {
    if (existsSync(candidate)) return resolve(candidate);
  }
  throw new Error('پوشهٔ docs/user پیدا نشد.');
}

export function readGuide(file: string): string {
  return readFileSync(join(docsDir(), file), 'utf-8');
}

export function guideBySlug(slug: string): Guide | undefined {
  return GUIDES.find((guide) => guide.slug === slug);
}

/**
 * پیوند درون سند ← مسیر برنامه. پیوند به راهنمای دیگر `/help/…` می‌شود؛
 * پیوند به سندهای فنی (`../ops/…`) منتشر نمی‌شود و متن ساده می‌ماند.
 */
export function resolveGuideLink(href: string): string | null {
  if (/^https?:\/\//.test(href) || href.startsWith('#')) return href;
  const [path = '', anchor] = href.split('#');
  if (path.includes('/')) return null;
  if (path === 'README.md') return anchor ? `/help#${anchor}` : '/help';
  const guide = GUIDES.find((g) => g.file === path);
  if (!guide) return null;
  return `/help/${guide.slug}${anchor ? `#${anchor}` : ''}`;
}
