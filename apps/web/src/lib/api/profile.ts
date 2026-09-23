/** فراخوان‌های /me — قرارداد §5.3. */

import type { OnboardingState } from './auth';
import { apiFetch } from './client';
import type { Recommendation } from './projects';

export type DegreeLevel = 'ASSOCIATE' | 'BACHELOR' | 'MASTER' | 'PHD' | 'OTHER';
export type WorkStyle = 'SOLO' | 'TEAM' | 'EITHER';
export type PrimaryGoal =
  'GRADE' | 'LEARNING' | 'PUBLICATION' | 'INCOME' | 'STARTUP' | 'EMPLOYMENT';

export interface Profile {
  first_name: string;
  last_name: string;
  display_name: string | null;
  avatar_url: string | null;
  university: { id: string; title_fa: string } | null;
  field_of_study: string | null;
  degree_level: DegreeLevel | null;
  degree_level_fa: string | null;
  entry_year: number | null;
  bio: string | null;
  work_style: WorkStyle | null;
  primary_goal: PrimaryGoal | null;
  weekly_hours: number | null;
  is_public: boolean;
  /** FR-PROF-03 — روشن یا خاموش بودن هر بخش نیمرخ عمومی (ADR-0017). */
  privacy: Record<string, boolean>;
}

export interface Me {
  id: string;
  mobile: string | null;
  email: string | null;
  email_verified: boolean;
  mobile_verified: boolean;
  username: string | null;
  profile: Profile | null;
  roles: { code: string; scope_type: string; scope_id: string | null }[];
  onboarding: {
    state: OnboardingState;
    completed_steps: number;
    total_steps: number;
    next_route: string;
  };
}

export interface ProfileUpdate {
  first_name?: string;
  last_name?: string;
  display_name?: string;
  birth_year?: number;
  gender?: 'M' | 'F' | 'UNDISCLOSED';
  bio?: string;
  university_id?: string;
  field_of_study?: string;
  degree_level?: DegreeLevel;
  student_number?: string;
  entry_year?: number;
  /** FR-TEAM-01 — فقط نیمرخ عمومی در جستجوی هم‌تیمی دیده می‌شود. */
  is_public?: boolean;
  /** فقط بخش‌های فرستاده‌شده تغییر می‌کنند. */
  privacy?: Partial<Record<string, boolean>>;
}

/**
 * پاسخ هر گام ارزیابی — §5.3.
 *
 * `preview_recommendations` همان «لحظهٔ طلایی» §01 است: سرور بلافاصله
 * پس از ذخیره، پیشنهاد برمی‌گرداند.
 */
export interface SurveyStepResult {
  completed_steps: number;
  total_steps: number;
  preview_recommendations: Recommendation[];
}

export interface SurveyState {
  skills: { skill_id: string; level: number; is_verified: boolean }[];
  asset_ids: string[];
  interests: { interest_id: string; level: number }[];
  work_style: WorkStyle | null;
  primary_goal: PrimaryGoal | null;
  weekly_hours: number | null;
  completed_steps: number;
  total_steps: number;
}

export function fetchMe(accessToken: string) {
  return apiFetch<Me>('/me', { accessToken });
}

export function updateProfile(patch: ProfileUpdate, accessToken: string) {
  return apiFetch<Profile>('/me/profile', { method: 'PATCH', accessToken, body: patch });
}

export function fetchSurvey(accessToken: string) {
  return apiFetch<SurveyState>('/me/survey', { accessToken });
}

export function saveSkills(skills: { skill_id: string; level: number }[], accessToken: string) {
  return apiFetch<SurveyStepResult>('/me/survey/skills', {
    method: 'PATCH',
    accessToken,
    body: { skills },
  });
}

export function saveAssets(assetIds: string[], accessToken: string) {
  return apiFetch<SurveyStepResult>('/me/survey/assets', {
    method: 'PATCH',
    accessToken,
    body: { asset_ids: assetIds },
  });
}

export function saveInterests(
  interests: { interest_id: string; level: number }[],
  accessToken: string,
) {
  return apiFetch<SurveyStepResult>('/me/survey/interests', {
    method: 'PATCH',
    accessToken,
    body: { interests },
  });
}

export function savePreferences(
  preferences: { work_style?: WorkStyle; primary_goal?: PrimaryGoal; weekly_hours?: number },
  accessToken: string,
) {
  return apiFetch<SurveyStepResult>('/me/survey/preferences', {
    method: 'PATCH',
    accessToken,
    body: preferences,
  });
}

/** §3.3 — متن گزینه‌های گام ۴. */
export const WORK_STYLE_OPTIONS: { value: WorkStyle; label: string }[] = [
  { value: 'SOLO', label: 'ترجیح می‌دهم انفرادی کار کنم' },
  { value: 'TEAM', label: 'ترجیح می‌دهم تیمی کار کنم' },
  { value: 'EITHER', label: 'فرقی ندارد' },
];

export const PRIMARY_GOAL_OPTIONS: { value: PrimaryGoal; label: string; hint: string }[] = [
  { value: 'GRADE', label: 'نمرهٔ درس', hint: 'می‌خواهم درس را خوب پاس کنم' },
  { value: 'LEARNING', label: 'یادگیری', hint: 'مهارت تازه می‌خواهم' },
  { value: 'PUBLICATION', label: 'مقاله', hint: 'دنبال انتشار علمی‌ام' },
  { value: 'INCOME', label: 'درآمد', hint: 'می‌خواهم درآمد واقعی داشته باشم' },
  { value: 'STARTUP', label: 'استارتاپ', hint: 'کسب‌وکار خودم را می‌سازم' },
  { value: 'EMPLOYMENT', label: 'استخدام', hint: 'رزومه و تجربهٔ کاری می‌خواهم' },
];

export const DEGREE_OPTIONS: { value: DegreeLevel; label: string }[] = [
  { value: 'ASSOCIATE', label: 'کاردانی' },
  { value: 'BACHELOR', label: 'کارشناسی' },
  { value: 'MASTER', label: 'کارشناسی ارشد' },
  { value: 'PHD', label: 'دکتری' },
  { value: 'OTHER', label: 'سایر' },
];
