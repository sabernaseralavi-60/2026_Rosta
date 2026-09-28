/**
 * عکس‌های سایت — کلیدهای ثابت که یادداشت‌های Vault در `cover:` به آن‌ها اشاره می‌کنند.
 *
 * فایل‌ها در `public/photos/` هستند. برای جایگزینی با عکس خودتان، فقط فایلی با
 * همان نام (مثلاً `hero.jpg`) و همان نسبت ابعاد بگذارید؛ نام‌بردن مجوز و سازندهٔ
 * عکس‌های فعلی در `public/photos/credits.json` و صفحهٔ `/credits` است.
 */

export type PhotoKey = 'hero' | 'learn' | 'research' | 'solve' | 'collab' | 'agri';

export interface Photo {
  src: string;
  alt: string;
  width: number;
  height: number;
}

export const PHOTOS: Record<PhotoKey, Photo> = {
  hero: {
    src: '/photos/hero.jpg',
    alt: 'کوه‌ها و دره‌های کالوت در دشت لوت کرمان، هنگام غروب',
    width: 1920,
    height: 1275,
  },
  learn: {
    src: '/photos/learn.jpg',
    alt: 'نور رنگی از شیشه‌های رنگی مسجد نصیرالملک روی فرش',
    width: 1920,
    height: 1288,
  },
  research: {
    src: '/photos/research.jpg',
    alt: 'نمای هوایی یک تقاطع بزرگ بزرگراهی در شهر',
    width: 1920,
    height: 1280,
  },
  solve: {
    src: '/photos/solve.jpg',
    alt: 'پل کابلی با بازتاب چراغ‌ها روی آب در شب',
    width: 1920,
    height: 1280,
  },
  collab: {
    src: '/photos/collab.jpg',
    alt: 'سقف کاشی‌کاری‌شدهٔ مسجد نصیرالملک',
    width: 1920,
    height: 1183,
  },
  agri: {
    src: '/photos/agri.jpg',
    alt: 'نخلستان و برج خشتی در کرمان',
    width: 1920,
    height: 1385,
  },
};

/** عکس پیش‌فرض هر نوع محتوا، وقتی یادداشت `cover` ندارد. */
const KIND_DEFAULT: Record<string, PhotoKey> = {
  ARTICLE: 'learn',
  BOOK_SUMMARY: 'collab',
  PAPER_SUMMARY: 'research',
  EXAMPLE: 'solve',
  CASE_STUDY: 'solve',
  DATASET_NOTE: 'research',
};

export function isPhotoKey(value: string | null | undefined): value is PhotoKey {
  return value != null && Object.hasOwn(PHOTOS, value);
}

/** کلید عکس یک محتوا؛ نشانی https بیرونی جدا در `externalCover` می‌آید. */
export function photoKeyFor(cover: string | null, kind: string): PhotoKey {
  if (isPhotoKey(cover)) return cover;
  return KIND_DEFAULT[kind] ?? 'learn';
}

export function externalCover(cover: string | null): string | null {
  return cover?.startsWith('https://') ? cover : null;
}
