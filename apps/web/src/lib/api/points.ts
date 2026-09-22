/**
 * فراخوان‌های امتیاز، نشان، رتبه‌بندی و داشبورد — M5، §5.3، §5.8، §5.11.
 *
 * اعداد امتیاز از سرور **رشته**‌اند (`"12.50"`)، مثل نمرهٔ آزمون. کلاینت
 * آن‌ها را فقط برای نمایش به عدد تبدیل می‌کند؛ سطح، «چند امتیاز تا سطح
 * بعد» و رتبه را سرور حساب می‌کند (§5.5).
 */

import { apiFetch } from './client';

export type PointCategory = 'LEARNING' | 'RESEARCH' | 'STARTUP' | 'COMMUNITY';
export type BadgeTier = 'BRONZE' | 'SILVER' | 'GOLD' | 'PLATINUM';
export type LeaderboardScope = 'GLOBAL' | 'OFFERING' | 'UNIVERSITY';
export type Health = 'HEALTHY' | 'AT_RISK' | 'STALLED';

export const CATEGORY_LABELS: Record<PointCategory, string> = {
  LEARNING: 'یادگیری',
  RESEARCH: 'پژوهش',
  STARTUP: 'کارآفرینی',
  COMMUNITY: 'جامعه',
};

/** ترتیب نمایش — آبی و بنفش کنار هم نمی‌نشینند (tokens.css). */
export const CATEGORIES: PointCategory[] = ['LEARNING', 'STARTUP', 'RESEARCH', 'COMMUNITY'];

export interface PointEntry {
  id: string;
  rule_code: string;
  rule_title_fa: string;
  category: PointCategory;
  category_fa: string;
  amount: string;
  source_type: string;
  source_type_fa: string | null;
  source_id: string | null;
  source_label: string | null;
  source_href: string | null;
  note: string | null;
  created_at: string;
  reverses_id: string | null;
  /** این ردیف بعداً اصلاح شده — خط می‌خورد، پاک نمی‌شود. */
  is_reversed: boolean;
}

export interface Level {
  level: number;
  title_fa: string;
  current_at: number;
  next_at: number | null;
  to_next: string;
  ratio: string;
}

export interface PointsSummary {
  total: string;
  level: Level;
  by_category: Record<PointCategory, string>;
  term_total: string;
  term_by_category: Record<PointCategory, string>;
  latest_entry_id: string | null;
  recent: PointEntry[];
}

export interface Badge {
  code: string;
  title_fa: string;
  description: string;
  icon: string;
  tier: BadgeTier;
  tier_fa: string;
  earned: boolean;
  awarded_at: string | null;
  /** کسب‌شده ولی جشنش هنوز دیده نشده. */
  seen: boolean;
  progress_current: string;
  progress_target: string;
  progress_ratio: string;
}

export interface LeaderRow {
  rank: number;
  user: { user_id: string; display_name: string | null; username: string | null };
  total: string;
  level: number;
  is_me: boolean;
}

export interface Leaderboard {
  scope: LeaderboardScope;
  scope_id: string | null;
  category: PointCategory | null;
  term_title_fa: string | null;
  entries: LeaderRow[];
  growth: LeaderRow[];
  me: {
    rank: number | null;
    total: string;
    level: number;
    percentile: number | null;
    hidden: boolean;
    /** انصراف خودش، یا کادر آموزشی که در رقابت دانشجویان نیست. */
    excluded_reason: 'OPTED_OUT' | 'STAFF' | null;
  };
}

export interface NextStep {
  kind: string;
  title: string;
  description: string;
  href: string;
  due_at: string | null;
}

export interface CourseCard {
  offering_id: string;
  course_title_fa: string;
  term_title_fa: string;
  study_ratio: string | null;
  learning_score: string | null;
  current_week_number: number | null;
}

export interface ProjectCard {
  project_id: string;
  title_fa: string;
  kind: string;
  status: string;
  health: Health;
  health_fa: string;
  next_milestone_title: string | null;
  next_milestone_due_on: string | null;
  next_milestone_status: string | null;
  approved_milestones: number;
  required_milestones: number;
}

export interface TrendPoint {
  week_start: string;
  total: string;
}

export interface UpcomingEvent {
  kind: 'QUIZ_OPENS' | 'QUIZ_CLOSES' | 'MILESTONE_DUE';
  title: string;
  at: string;
  href: string;
}

export interface StudentDashboard {
  next_step: NextStep | null;
  points: PointsSummary;
  courses: CourseCard[];
  projects: ProjectCard[];
  recent_badges: Badge[];
  trend: TrendPoint[];
  upcoming: UpcomingEvent[];
}

export interface LearningComponent {
  key: 'quiz' | 'study' | 'project' | 'attendance';
  title_fa: string;
  /** `null` یعنی این مؤلفه در این درس نیست و وزنش بازتوزیع شد. */
  ratio: string | null;
  weight: string;
  earned: string;
  possible: string;
}

export interface LearningScore {
  offering_id: string;
  student_id: string;
  display_name: string | null;
  score: string | null;
  suggested_grade: string | null;
  components: LearningComponent[];
}

export interface LedgerFilters {
  category?: PointCategory;
  source_type?: string;
  source_id?: string;
  cursor?: string;
  limit?: number;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export function fetchPointsSummary(accessToken: string): Promise<PointsSummary> {
  return apiFetch('/me/points/summary', { accessToken });
}

export function fetchLedger(
  accessToken: string,
  filters: LedgerFilters = {},
): Promise<{ items: PointEntry[]; next_cursor: string | null }> {
  return apiFetch(`/me/points${query({ ...filters })}`, { accessToken });
}

export function fetchBadges(
  accessToken: string,
): Promise<{ earned: Badge[]; locked: Badge[] }> {
  return apiFetch('/me/badges', { accessToken });
}

export function markBadgesSeen(accessToken: string, codes?: string[]): Promise<{ updated: number }> {
  return apiFetch('/me/badges/seen', { method: 'POST', accessToken, body: { codes: codes ?? null } });
}

export function fetchLeaderboard(
  accessToken: string,
  params: { scope?: LeaderboardScope; scope_id?: string; category?: PointCategory } = {},
): Promise<Leaderboard> {
  return apiFetch(`/leaderboard${query(params)}`, { accessToken });
}

export function fetchDashboard(accessToken: string): Promise<StudentDashboard> {
  return apiFetch('/me/dashboard', { accessToken });
}

export function fetchMyLearningScore(
  accessToken: string,
  offeringId: string,
): Promise<LearningScore> {
  return apiFetch(`/me/learning-score/${offeringId}`, { accessToken });
}

/** `"12.50"` → `12.5`. `null` و متن نامعتبر صفر می‌شوند. */
export function points(value: string | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
