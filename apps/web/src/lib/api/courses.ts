/** فراخوان‌های /courses، /offerings، /resources و /materials — قرارداد §5.5. */

import { apiFetch } from './client';
import type { Page } from './projects';

export type AccessTier = 'PUBLIC' | 'SUBSCRIBER' | 'ENROLLED';
export type AccessReason = 'PUBLIC' | 'ENROLLED' | 'SUBSCRIPTION' | 'STAFF';
export type AccessBlocker = 'SUBSCRIPTION' | 'ENROLLMENT';
export type MaterialKind =
  | 'BOOK'
  | 'NOTE'
  | 'SLIDE'
  | 'VIDEO'
  | 'PODCAST'
  | 'DATASET'
  | 'CODE'
  | 'QUESTION_BANK'
  | 'LINK'
  | 'OTHER';
export type ResourceKind = 'PDF' | 'VIDEO' | 'LINK' | 'SLIDE' | 'DATASET' | 'CODE' | 'OTHER';
export type WeekStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
export type EnrollmentStatus = 'PENDING' | 'ACTIVE' | 'DROPPED' | 'COMPLETED' | 'REJECTED';
export type ProgressStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

/**
 * سنجش دسترسی یک محتوا — ADR-0009.
 *
 * `note_fa` را **سرور** می‌سازد و مستقیماً نمایش داده می‌شود. رابط
 * کاربری قفل را نمی‌سازد، فقط نشانش می‌دهد؛ وگرنه قاعدهٔ «رایگان برای
 * دانشجوی درس» دو جا نوشته می‌شود و یکی‌شان کهنه می‌ماند.
 */
export interface Access {
  allowed: boolean;
  tier: AccessTier;
  reason: AccessReason | null;
  blocker: AccessBlocker | null;
  note_fa: string;
}

export interface Material {
  id: string;
  kind: MaterialKind;
  kind_fa: string;
  title_fa: string;
  description: string | null;
  authors: string[];
  edition: string | null;
  language: string;
  size_bytes: number | null;
  page_count: number | null;
  duration_sec: number | null;
  is_downloadable: boolean;
  /** فقط وقتی `access.allowed` باشد پر است. */
  external_url: string | null;
  section: string | null;
  is_required: boolean;
  access: Access;
}

export interface CourseSummary {
  id: string;
  slug: string;
  code: string;
  title_fa: string;
  title_en: string | null;
  description: string | null;
  degree_level: string | null;
  degree_level_fa: string | null;
  credits: number | null;
  topics: string[];
  material_count: number;
  free_material_count: number;
  open_offering_count: number;
}

export interface OfferingRef {
  id: string;
  term_code: string;
  term_title_fa: string;
  instructor_name: string | null;
  status: string;
  requires_approval: boolean;
  has_enrollment_code: boolean;
  capacity: number | null;
  active_students: number;
}

export interface PlanRef {
  id: string;
  code: string;
  title_fa: string;
  price_irr: number;
  duration_days: number;
  scope: 'ALL_COURSES' | 'SINGLE_COURSE';
}

export interface CourseDetail extends CourseSummary {
  materials: Material[];
  offerings: OfferingRef[];
  plans: PlanRef[];
  my_enrollment_offering_id: string | null;
}

export interface WeekSummary {
  id: string;
  week_number: number;
  title_fa: string;
  description: string | null;
  status: WeekStatus;
  published_at: string | null;
  publish_at: string | null;
  resource_count: number;
  material_count: number;
  completed_count: number;
  progress_percent: number;
}

export interface Announcement {
  id: string;
  title: string;
  body: string;
  priority: 'NORMAL' | 'IMPORTANT' | 'URGENT';
  published_at: string;
  expires_at: string | null;
  /** پر یعنی پس از انتشار ویرایش شده — ADR-0021. */
  edited_at?: string | null;
}

export interface OfferingSummary {
  id: string;
  course_id: string;
  course_slug: string;
  course_title_fa: string;
  term_code: string;
  term_title_fa: string;
  instructor_id: string;
  instructor_name: string | null;
  status: string;
  requires_approval: boolean;
  has_enrollment_code: boolean;
  capacity: number | null;
  active_students: number;
  my_status: EnrollmentStatus | null;
  progress_percent: number;
  current_week_number: number | null;
}

export interface OfferingDetail extends OfferingSummary {
  description: string | null;
  grading_policy: Record<string, number>;
  weeks: WeekSummary[];
  announcements: Announcement[];
  final_grade: number | null;
}

export interface ResourceProgress {
  status: ProgressStatus;
  percent: number;
  position_sec: number | null;
  completed_at: string | null;
}

export interface CourseResource {
  id: string;
  kind: ResourceKind;
  title_fa: string;
  description: string | null;
  external_url: string | null;
  duration_sec: number | null;
  is_downloadable: boolean;
  is_required: boolean;
  has_file: boolean;
  progress: ResourceProgress | null;
}

export interface WeekDetail {
  week_number: number;
  title_fa: string;
  description: string | null;
  objectives: string[];
  status: WeekStatus;
  published_at: string | null;
  resources: CourseResource[];
  materials: Material[];
}

export interface DownloadTicket {
  download_url: string;
  expires_in: number;
  original_name: string;
}

// ── ویترین (بدون ورود هم کار می‌کند) ─────────────────────────────────
export interface CourseFilters {
  q?: string;
  degree_level?: string;
  page?: number;
  page_size?: number;
}

export function fetchCourses(filters: CourseFilters = {}, accessToken?: string | null) {
  const query = new URLSearchParams();
  if (filters.q) query.set('q', filters.q);
  if (filters.degree_level) query.set('degree_level', filters.degree_level);
  query.set('page', String(filters.page ?? 1));
  query.set('page_size', String(filters.page_size ?? 20));
  return apiFetch<Page<CourseSummary>>(`/courses?${query.toString()}`, { accessToken });
}

export function fetchCourse(slug: string, accessToken?: string | null) {
  return apiFetch<CourseDetail>(`/courses/${encodeURIComponent(slug)}`, { accessToken });
}

// ── کلاس ──────────────────────────────────────────────────────────────
export function fetchMyOfferings(accessToken: string) {
  return apiFetch<OfferingSummary[]>('/offerings/mine', { accessToken });
}

export function fetchOpenOfferings(accessToken: string) {
  return apiFetch<OfferingSummary[]>('/offerings', { accessToken });
}

export function fetchOffering(offeringId: string, accessToken: string) {
  return apiFetch<OfferingDetail>(`/offerings/${offeringId}`, { accessToken });
}

export function fetchWeek(offeringId: string, weekNumber: number, accessToken: string) {
  return apiFetch<WeekDetail>(`/offerings/${offeringId}/weeks/${weekNumber}`, { accessToken });
}

export function enroll(offeringId: string, accessToken: string, enrollmentCode?: string) {
  return apiFetch<{ id: string; status: EnrollmentStatus }>(`/offerings/${offeringId}/enroll`, {
    method: 'POST',
    accessToken,
    body: { enrollment_code: enrollmentCode ?? null },
  });
}

export function drop(offeringId: string, accessToken: string) {
  return apiFetch<void>(`/offerings/${offeringId}/enroll`, { method: 'DELETE', accessToken });
}

// ── مطالعه ────────────────────────────────────────────────────────────
export function recordProgress(
  resourceId: string,
  accessToken: string,
  payload: { percent?: number; position_sec?: number; completed?: boolean } = {},
) {
  return apiFetch<ResourceProgress>(`/resources/${resourceId}/progress`, {
    method: 'POST',
    accessToken,
    body: payload,
  });
}

export function resourceDownloadUrl(resourceId: string, accessToken: string) {
  return apiFetch<DownloadTicket>(`/resources/${resourceId}/download`, { accessToken });
}

/**
 * دانلود محتوای کتابخانه — اینجاست که دروازهٔ اشتراک باز یا بسته می‌شود.
 *
 * ۴۰۲ یعنی «اشتراک لازم است» و ۴۰۳ یعنی «فقط دانشجوی درس». هر دو پیام
 * فارسی آمادهٔ نمایش دارند و کلاینت نباید متن تازه‌ای بنویسد.
 */
export function materialDownloadUrl(materialId: string, accessToken: string) {
  return apiFetch<DownloadTicket>(`/materials/${materialId}/download`, { accessToken });
}
