/** فراخوان‌های /taxonomy — قرارداد §5.4. */

import { apiFetch } from './client';

export interface Skill {
  id: string;
  code: string;
  title_fa: string;
  title_en: string;
  category: string;
  icon: string | null;
  sort_order: number;
  /** در گام ۱ نیمرخ پیش‌فرض دیده می‌شود؛ بقیه پشت «مهارت‌های بیشتر». */
  is_core: boolean;
}

export interface Asset {
  id: string;
  code: string;
  title_fa: string;
  category: string;
  icon: string | null;
  sort_order: number;
}

export interface Interest {
  id: string;
  code: string;
  title_fa: string;
  icon: string | null;
  sort_order: number;
}

export interface University {
  id: string;
  title_fa: string;
  title_en: string | null;
  city: string | null;
  province: string | null;
}

/**
 * متن توصیفی هر سطح — FR-PROF-01.
 *
 * از سرور می‌آید و در کلاینت ثابت نمی‌شود: تعریف «سطح ۳» باید در فرم،
 * در دلیل توصیه‌گر و در نیمرخ عمومی یکی باشد.
 */
export interface LevelLabel {
  level: number;
  label: string;
}

export interface SkillList {
  items: Skill[];
  level_labels: LevelLabel[];
}

export interface InterestList {
  items: Interest[];
  level_labels: LevelLabel[];
}

export function fetchSkills() {
  return apiFetch<SkillList>('/taxonomy/skills');
}

export function fetchAssets() {
  return apiFetch<Asset[]>('/taxonomy/assets');
}

export function fetchInterests() {
  return apiFetch<InterestList>('/taxonomy/interests');
}

export function searchUniversities(q: string) {
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : '';
  return apiFetch<University[]>(`/taxonomy/universities${query}`);
}
