/**
 * «طرح مسئله / نیاز» و «همکاری با ما» — ADR-0030. هر دو بی‌ورودند.
 */

import { apiFetch } from './client';

export const NEED_TYPES = [
  { value: 'Commercial', label: 'تجاری' },
  { value: 'Research', label: 'پژوهشی' },
  { value: 'Education', label: 'آموزشی' },
  { value: 'Consulting', label: 'مشاوره' },
  { value: 'Collaboration', label: 'همکاری' },
  { value: 'Other', label: 'سایر' },
] as const;

export type NeedType = (typeof NEED_TYPES)[number]['value'];

export const SERVICES = [
  'Website / Web App',
  'AI',
  'Data Analysis',
  'Automation',
  'Content',
  'Research',
  'Engineering',
  'GIS',
  'Consulting',
  'Training',
  'Other',
] as const;

export type Service = (typeof SERVICES)[number];

/** نمونه‌جمله‌ها: کلیک روی هر کدام فرم را پیش‌پر می‌کند (فایل مشخصات فاز ۰، بند ۲۱). */
export const INTAKE_EXAMPLES: { text: string; type: NeedType; services: Service[] }[] = [
  {
    text: 'دانشجوی دکتری دانشگاه دیگری هستم و روی موضوع X کار می‌کنم.',
    type: 'Research',
    services: ['Research'],
  },
  { text: 'برای یک مقاله به تحلیل داده نیاز دارم.', type: 'Research', services: ['Data Analysis'] },
  {
    text: 'یک Dataset دارم و دنبال همکاری پژوهشی هستم.',
    type: 'Collaboration',
    services: ['Research', 'Data Analysis'],
  },
  {
    text: 'برای کسب‌وکارم به یک وب‌سایت یا Web App نیاز دارم.',
    type: 'Commercial',
    services: ['Website / Web App'],
  },
  {
    text: 'می‌خواهم فرآیند فروش و پیگیری مشتریانم Automation شود.',
    type: 'Commercial',
    services: ['Automation'],
  },
  {
    text: 'می‌خواهم بدانم کدام بخش‌های کسب‌وکارم با AI قابل بهبود است.',
    type: 'Consulting',
    services: ['AI', 'Consulting'],
  },
  {
    text: 'برای شرکت خود به Dashboard و تحلیل داده نیاز دارم.',
    type: 'Commercial',
    services: ['Data Analysis'],
  },
  {
    text: 'برای یک پروژه عمرانی به مطالعات، تحلیل یا طراحی نیاز دارم.',
    type: 'Commercial',
    services: ['Engineering', 'GIS'],
  },
  {
    text: 'یک ایده تجاری دارم و می‌خواهم آن را توسعه دهم.',
    type: 'Commercial',
    services: ['Consulting'],
  },
  {
    text: 'مورد من در این فهرست نیست و خودم آن را توضیح می‌دهم.',
    type: 'Other',
    services: ['Other'],
  },
];

export const COLLAB_WAYS = [
  'همکاری در پروژه‌ها',
  'پژوهش مشترک',
  'مشاوره تخصصی',
  'عضویت در تیم',
  'توسعهٔ نرم‌افزار',
  'Data Science',
  'توسعهٔ AI',
  'پروژه‌های عمرانی و حمل‌ونقل',
  'تدریس و تولید محتوا',
  'ادامهٔ همکاری پس از تحصیل',
] as const;

export const HOURS = [
  { value: 'LT2', label: 'کمتر از ۲ ساعت در هفته' },
  { value: '2_5', label: '۲ تا ۵ ساعت' },
  { value: '5_10', label: '۵ تا ۱۰ ساعت' },
  { value: 'GT10', label: 'بیش از ۱۰ ساعت' },
] as const;

export interface Contact {
  name: string;
  mobile?: string;
  email?: string;
  organization?: string;
  /** تلهٔ ربات — همیشه تهی. */
  website: string;
}

export interface IntakePayload extends Contact {
  need_type: NeedType;
  services: Service[];
  summary: string;
  expected_result?: string;
  sector?: string;
  has_data?: 'YES' | 'NO' | 'UNSURE';
  timeline?: string;
  budget?: string;
  notes?: string;
}

export interface CollaborationPayload extends Contact {
  intro: string;
  specialty?: string;
  skills?: string;
  experience?: string;
  interests?: string;
  ways: string[];
  hours_per_week?: 'LT2' | '2_5' | '5_10' | 'GT10';
  portfolio_url?: string;
}

export interface Submission {
  tracking_code: string;
  /** کد شخصی صاحب درخواست: حساب وصل‌شده، وگرنه کد شخصِ بی‌حساب (ADR-0034). */
  person_code: string | null;
  /** درست فقط وقتی شمارهٔ تأییدشدهٔ یک حساب با تماس یکی بود. */
  account_linked: boolean;
  message: string;
}

export function submitIntake(payload: IntakePayload) {
  return apiFetch<Submission>('/public/intake', { method: 'POST', body: payload });
}

export function submitCollaboration(payload: CollaborationPayload) {
  return apiFetch<Submission>('/public/collaboration', { method: 'POST', body: payload });
}
