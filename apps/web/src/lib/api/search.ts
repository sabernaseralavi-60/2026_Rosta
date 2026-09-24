/**
 * جستجوی سراسری ⌘K — §3.7، M7-13.
 *
 * نتیجه‌ها از سرور می‌آیند و گروه‌بندی‌شده‌اند؛ «دستورات» ثابت‌اند و در
 * همین فایل‌اند، چون به نقش بستگی دارند نه به داده. تطبیق دستور با همان
 * یکسان‌سازی فارسی سرور انجام می‌شود تا «ي» عربی هم «ثبت ایده» را پیدا کند.
 */

import { canSeeAdmin } from './admin';
import { apiFetch } from './client';
import { canSeeTeach } from './teach';

export type SearchKind =
  'COURSE' | 'PROJECT' | 'IDEA' | 'VENTURE' | 'TOPIC' | 'PERSON' | 'MATERIAL';

export interface SearchHit {
  id: string;
  title: string;
  subtitle: string | null;
  href: string;
}

export interface SearchGroup {
  kind: SearchKind;
  title_fa: string;
  items: SearchHit[];
}

export const MIN_QUERY_LENGTH = 2;

export function searchAll(q: string, token: string, signal?: AbortSignal) {
  return apiFetch<{ q: string; groups: SearchGroup[] }>(`/search?q=${encodeURIComponent(q)}`, {
    accessToken: token,
    signal,
  });
}

export interface Command {
  id: string;
  label: string;
  href: string;
  /** واژه‌های دیگری که کاربر ممکن است تایپ کند. */
  keywords: string;
  adminOnly?: boolean;
  /** فقط برای استاد و دستیار — ADR-0019. */
  teachOnly?: boolean;
}

export const COMMANDS: Command[] = [
  { id: 'dashboard', label: 'رفتن به داشبورد', href: '/dashboard', keywords: 'خانه شروع' },
  { id: 'idea-new', label: 'ثبت ایده', href: '/ideas/new', keywords: 'ایده جدید بانک ایده' },
  { id: 'project-new', label: 'ساخت پروژه', href: '/projects/new', keywords: 'پروژه جدید' },
  { id: 'projects', label: 'بانک پروژه‌ها', href: '/projects', keywords: 'پروژه پیشنهاد' },
  { id: 'courses', label: 'دروس من', href: '/courses', keywords: 'درس کلاس آموزش' },
  { id: 'library', label: 'کتابخانهٔ دروس', href: '/library', keywords: 'جزوه منبع کتاب' },
  { id: 'research', label: 'مسیر پژوهش', href: '/research', keywords: 'مقاله سطح پژوهش' },
  {
    id: 'topics',
    label: 'بانک موضوع پژوهشی',
    href: '/research/topics',
    keywords: 'موضوع پایان‌نامه',
  },
  { id: 'teammates', label: 'جستجوی هم‌تیمی', href: '/teams/find', keywords: 'تیم هم‌تیمی' },
  {
    id: 'venture-new',
    label: 'ثبت کسب‌وکار',
    href: '/ventures/new',
    keywords: 'استارتاپ کسب‌وکار',
  },
  { id: 'city', label: 'آزمایشگاه شهر هوشمند', href: '/city', keywords: 'شهر SUMO ترافیک' },
  { id: 'notifications', label: 'اعلان‌ها', href: '/notifications', keywords: 'پیام خبر' },
  // M7-19 — راهنمای فارسی از docs/user.
  { id: 'help', label: 'راهنما', href: '/help', keywords: 'کمک راهنمای کاربری سؤال پرسش' },
  {
    id: 'certificates',
    label: 'گواهی‌های من',
    href: '/me/certificates',
    keywords: 'گواهی مدرک رزومه',
  },
  {
    id: 'public-profile',
    label: 'نیمرخ عمومی من',
    href: '/me/public-profile',
    keywords: 'پروفایل حریم خصوصی',
  },
  { id: 'points', label: 'دفتر امتیاز', href: '/me/points', keywords: 'امتیاز سطح' },
  { id: 'leaderboard', label: 'رتبه‌بندی', href: '/leaderboard', keywords: 'رتبه جدول' },
  { id: 'settings', label: 'تنظیمات اعلان', href: '/me/settings', keywords: 'پیامک ایمیل تلگرام' },
  {
    id: 'teach',
    label: 'ناحیهٔ تدریس',
    href: '/teach',
    keywords: 'استاد تدریس کلاس',
    teachOnly: true,
  },
  {
    id: 'teach-offerings',
    label: 'ارائه‌های من (تدریس)',
    href: '/teach/offerings',
    keywords: 'ارائه درس هفته حضور غیاب دفتر نمره',
    teachOnly: true,
  },
  {
    id: 'teach-quizzes',
    label: 'آزمون‌ها و تصحیح',
    href: '/teach/quizzes',
    keywords: 'آزمون سؤال تصحیح اعتراض',
    teachOnly: true,
  },
  {
    id: 'teach-bank',
    label: 'بانک سؤال',
    href: '/teach/question-bank',
    keywords: 'سؤال بانک',
    teachOnly: true,
  },
  {
    id: 'admin-subscriptions',
    label: 'تأیید اشتراک‌ها',
    href: '/admin/subscriptions',
    keywords: 'اشتراک پرداخت فیش',
    adminOnly: true,
  },
  { id: 'admin', label: 'پنل مدیریت', href: '/admin', keywords: 'مدیر شاخص', adminOnly: true },
  {
    id: 'admin-users',
    label: 'مدیریت کاربران',
    href: '/admin/users',
    keywords: 'کاربر نقش',
    adminOnly: true,
  },
  {
    id: 'admin-audit',
    label: 'لاگ حسابرسی',
    href: '/admin/audit',
    keywords: 'لاگ حسابرسی',
    adminOnly: true,
  },
];

/** یکسان‌سازی فارسی سمت کلاینت — هم‌راستا با `fa_normalize` سرور (ADR-0003). */
export function normalizeFa(value: string): string {
  return value
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/[ۀة]/g, 'ه')
    .replace(/[أإٱآ]/g, 'ا')
    .replace(/[ً-ٰٟـ]/g, '')
    .replace(/[‌\s]+/g, ' ')
    .trim()
    .toLowerCase();
}

export function matchCommands(q: string, roles: string[] | undefined | null): Command[] {
  const admin = canSeeAdmin(roles);
  const teach = canSeeTeach(roles);
  const visible = COMMANDS.filter(
    (command) => (admin || !command.adminOnly) && (teach || !command.teachOnly),
  );
  const needle = normalizeFa(q);
  if (!needle) return visible.slice(0, 6);
  return visible.filter((command) =>
    normalizeFa(`${command.label} ${command.keywords}`).includes(needle),
  );
}
