/** فراخوان‌های /projects و /recommendations — قرارداد §5.7. */

import { apiFetch } from './client';

export type ProjectKind = 'A_VENTURE' | 'B_RESEARCH' | 'C_PROBLEM' | 'D_PERSONAL';
export type WorkStyle = 'SOLO' | 'TEAM' | 'EITHER';
export type Polarity = 'POSITIVE' | 'WARNING';
export type FeedbackVerdict = 'NOT_RELEVANT' | 'INTERESTED' | 'DISMISSED';

export interface ProjectSummary {
  id: string;
  slug: string;
  title_fa: string;
  summary: string;
  kind: ProjectKind;
  kind_fa: string;
  status: string;
  difficulty: number;
  difficulty_fa: string;
  time_commitment_hpw: number | null;
  work_style: WorkStyle;
  team_size_min: number;
  team_size_max: number;
  active_members: number;
  open_seats: number;
  tags: string[];
  deadline_on: string | null;
  applications_close_at: string | null;
}

/**
 * دلیل تطابق — §8.10.
 *
 * `text` را **سرور** می‌سازد و مستقیماً نمایش داده می‌شود. کلاینت آن را
 * بازنویسی یا ترجمه نمی‌کند: منطق توضیح باید یکجا بماند.
 */
export interface Reason {
  type: string;
  polarity: Polarity;
  contribution: number;
  text: string;
}

/** شش زیرامتیاز §8.2 تا §8.7 — برای شفافیت امتیاز (اصل ۳ §00). */
export interface Breakdown {
  skill: number;
  asset: number;
  interest: number;
  time: number;
  style: number;
  goal: number;
}

/**
 * تطابق من با یک پروژه — §5.7.
 *
 * `exclusion_note` وقتی پر است که امتیاز صفر شده باشد چون پروژه از فهرست
 * پیشنهاد حذف شده (امکانات الزامی ندارد، یا کاربر خودش ردش کرده). بدون
 * آن، «۰٪» در کنار زیرامتیازهای بالا فقط گیج‌کننده است.
 */
export interface Match {
  match_score: number;
  breakdown: Breakdown;
  reasons: Reason[];
  is_stretch: boolean;
  is_excluded: boolean;
  exclusion_note: string | null;
}

export interface Recommendation {
  project: ProjectSummary;
  match_score: number;
  reasons: Reason[];
  breakdown: Breakdown;
  /** §8.11 — «چالش‌برانگیز، اگر آماده‌ای». */
  is_stretch: boolean;
}

export interface RecommendationsResult {
  items: Recommendation[];
  profile_completeness: number;
  computed_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  description: string;
  expected_output: string;
  rewards: Record<string, unknown>;
  required_skills: {
    skill_id: string;
    title_fa: string;
    min_level: number;
    weight: number;
    is_teachable: boolean;
  }[];
  required_assets: { asset_id: string; title_fa: string; is_mandatory: boolean }[];
  interests: { interest_id: string; title_fa: string }[];
  match: Match | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export function fetchRecommendations(accessToken: string, limit = 10) {
  return apiFetch<RecommendationsResult>(`/projects/recommended?limit=${limit}`, { accessToken });
}

export interface ProjectFilters {
  kind?: ProjectKind;
  work_style?: WorkStyle;
  difficulty_max?: number;
  skill_id?: string;
  interest_id?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export function fetchProjects(filters: ProjectFilters = {}, accessToken?: string | null) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return apiFetch<Page<ProjectSummary>>(`/projects${query ? `?${query}` : ''}`, { accessToken });
}

export function fetchProject(id: string, accessToken?: string | null) {
  return apiFetch<ProjectDetail>(`/projects/${id}`, { accessToken });
}

export function sendRecommendationFeedback(
  projectId: string,
  verdict: FeedbackVerdict,
  accessToken: string,
  reason?: string,
) {
  return apiFetch<void>(`/recommendations/${projectId}/feedback`, {
    method: 'POST',
    accessToken,
    body: { verdict, reason },
  });
}
