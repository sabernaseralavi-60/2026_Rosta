/**
 * تعریف درس، نیم‌سال و ارائه — §3.6 `/admin/courses`، §5.12، ADR-0020.
 *
 * فقط مدیر آموزشی و مدیر سامانه. ارائه اینجا ساخته و به استاد سپرده می‌شود؛
 * وضعیت، ثبت‌نام و هفته‌هایش پس از آن در `/teach` با خود استاد است.
 */

import { apiFetch } from './client';
import type { OfferingStatus } from './teach';

/** نقش‌هایی که `/admin/courses` را می‌بینند؛ سرور هر مسیر را جدا می‌سنجد. */
export const COURSE_ADMIN_ROLES = ['ADMIN', 'COORDINATOR'];

export function canDefineCourses(roles: string[] | undefined | null): boolean {
  return (roles ?? []).some((role) => COURSE_ADMIN_ROLES.includes(role));
}

export type DegreeLevel = 'BACHELOR' | 'MASTER' | 'PHD' | 'PUBLIC';
export type AccessTier = 'PUBLIC' | 'SUBSCRIBER' | 'ENROLLED';
export type WeekSource = 'SYLLABUS' | 'OFFERING' | 'NONE';

export const DEGREE_LABELS: Record<DegreeLevel, string> = {
  BACHELOR: 'کارشناسی',
  MASTER: 'کارشناسی ارشد',
  PHD: 'دکتری',
  PUBLIC: 'عمومی',
};

export const ACCESS_TIER_LABELS: Record<AccessTier, string> = {
  PUBLIC: 'رایگان برای همه',
  SUBSCRIBER: 'رایگان برای دانشجوی درس، با اشتراک برای بقیه',
  ENROLLED: 'فقط دانشجوی ثبت‌نام‌شده',
};

// ── نیم‌سال ───────────────────────────────────────────────────────────
export interface AdminTerm {
  id: string;
  code: string;
  title_fa: string;
  /** `YYYY-MM-DD` */
  starts_on: string;
  ends_on: string;
  is_current: boolean;
  offering_count: number;
}

export interface TermInput {
  code: string;
  title_fa: string;
  starts_on: string;
  ends_on: string;
  is_current?: boolean;
}

export function fetchTerms(accessToken: string) {
  return apiFetch<AdminTerm[]>('/admin/terms', { accessToken });
}

export function createTerm(accessToken: string, body: TermInput) {
  return apiFetch<AdminTerm>('/admin/terms', { method: 'POST', accessToken, body });
}

export function updateTerm(accessToken: string, termId: string, body: Partial<TermInput>) {
  return apiFetch<AdminTerm>(`/admin/terms/${termId}`, { method: 'PATCH', accessToken, body });
}

export function deleteTerm(accessToken: string, termId: string) {
  return apiFetch<void>(`/admin/terms/${termId}`, { method: 'DELETE', accessToken });
}

/** نیم‌سالی که تمام شده ارائهٔ تازه نمی‌گیرد (`TERM_ENDED`). */
export function termIsOver(term: AdminTerm, today: string): boolean {
  return term.ends_on < today;
}

// ── درس ───────────────────────────────────────────────────────────────
export interface AdminCourse {
  id: string;
  code: string;
  slug: string;
  title_fa: string;
  title_en: string | null;
  description: string | null;
  degree_level: DegreeLevel | null;
  credits: number | null;
  is_public: boolean;
  is_active: boolean;
  default_access_tier: AccessTier;
  topics: string[];
  /** نام پوشه در `Courses/`؛ درس پوشه‌ای در پنل فقط‌خواندنی است. */
  source_dir: string | null;
  offering_count: number;
  material_count: number;
  /** هفته‌های برنامهٔ درسی `course.yml`؛ `null` یعنی پوشه‌ای روی سرور نیست. */
  syllabus_weeks: number | null;
  created_at: string;
}

export interface CourseInput {
  code: string;
  slug?: string;
  title_fa: string;
  title_en?: string | null;
  description?: string | null;
  degree_level?: DegreeLevel | null;
  credits?: number | null;
  is_public?: boolean;
  is_active?: boolean;
  default_access_tier?: AccessTier;
  topics?: string[];
}

export function fetchAdminCourses(accessToken: string) {
  return apiFetch<AdminCourse[]>('/admin/courses', { accessToken });
}

export function createCourse(accessToken: string, body: CourseInput) {
  return apiFetch<AdminCourse>('/admin/courses', { method: 'POST', accessToken, body });
}

export function updateCourse(accessToken: string, courseId: string, body: Partial<CourseInput>) {
  return apiFetch<AdminCourse>(`/admin/courses/${courseId}`, {
    method: 'PATCH',
    accessToken,
    body,
  });
}

/** `TRAFFIC-ENG` ← `traffic-eng` — همان قاعدهٔ سرور برای نشانی پیش‌فرض. */
export function slugFromCode(code: string): string {
  return code
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// ── ارائه ─────────────────────────────────────────────────────────────
export interface AdminOffering {
  id: string;
  course_id: string;
  course_code: string;
  course_title_fa: string;
  term_id: string;
  term_code: string;
  term_title_fa: string;
  instructor_id: string;
  instructor_name: string | null;
  status: OfferingStatus;
  capacity: number | null;
  requires_approval: boolean;
  has_enrollment_code: boolean;
  active_students: number;
  pending_students: number;
  week_count: number;
  published_weeks: number;
  created_at: string;
}

export interface OfferingInput {
  course_id: string;
  term_id: string;
  instructor_id: string;
  status?: 'DRAFT' | 'OPEN';
  capacity?: number | null;
  enrollment_code?: string | null;
  requires_approval?: boolean;
  weeks_from?: WeekSource;
  copy_from_offering_id?: string | null;
}

export function fetchAdminOfferings(
  accessToken: string,
  filters: { term_id?: string; course_id?: string } = {},
) {
  const params = new URLSearchParams();
  if (filters.term_id) params.set('term_id', filters.term_id);
  if (filters.course_id) params.set('course_id', filters.course_id);
  const query = params.toString();
  return apiFetch<AdminOffering[]>(`/admin/offerings${query ? `?${query}` : ''}`, {
    accessToken,
  });
}

export function createOffering(accessToken: string, body: OfferingInput) {
  return apiFetch<AdminOffering & { weeks_created: number }>('/admin/offerings', {
    method: 'POST',
    accessToken,
    body,
  });
}

export function reassignOffering(
  accessToken: string,
  offeringId: string,
  body: { instructor_id?: string; term_id?: string },
) {
  return apiFetch<AdminOffering>(`/admin/offerings/${offeringId}`, {
    method: 'PATCH',
    accessToken,
    body,
  });
}

export function deleteOffering(accessToken: string, offeringId: string) {
  return apiFetch<void>(`/admin/offerings/${offeringId}`, { method: 'DELETE', accessToken });
}

// ── گزینش استاد ───────────────────────────────────────────────────────
export interface InstructorCandidate {
  id: string;
  name: string | null;
  username: string | null;
  /** پوشانده برای مدیر آموزشی. */
  mobile: string | null;
  active_offerings: number;
}

export function searchInstructors(accessToken: string, q: string) {
  return apiFetch<InstructorCandidate[]>(
    `/admin/instructor-candidates?q=${encodeURIComponent(q)}`,
    { accessToken },
  );
}
