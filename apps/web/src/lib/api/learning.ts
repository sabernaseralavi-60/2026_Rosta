/** فراخوان‌های حلقهٔ یادگیری روزانه — ADR-0036. */

import { apiFetch } from './client';

export type MasteryLevel = 'STRONG' | 'MEDIUM' | 'WEAK' | 'LOW_DATA';
export type CheckpointState = 'AVAILABLE' | 'IN_PROGRESS' | 'DONE' | 'UPCOMING';

export const MASTERY_LABELS: Record<MasteryLevel, string> = {
  STRONG: 'قوی',
  MEDIUM: 'متوسط',
  WEAK: 'نیازمند تمرین',
  LOW_DATA: 'هنوز کم‌داده',
};

export interface Mastery {
  competency_id: string;
  code: string;
  title: string;
  score: number;
  evidence_n: number;
  level: MasteryLevel;
}

export interface CheckpointCard {
  quiz_id: string;
  title: string;
  state: CheckpointState;
  opens_at: string;
  closes_at: string;
  duration_min: number;
  question_count: number;
  attempt_id: string | null;
}

export interface TodayOffering {
  offering_id: string;
  course_title: string;
  lesson: { id: string; title: string; est_minutes: number; published_at: string } | null;
  checkpoint: CheckpointCard | null;
  streak: { current: number; longest: number; alive: boolean };
  last_result: {
    quiz_title: string;
    day: string;
    correct: number;
    total: number;
    skills: { title: string; correct: number; total: number }[];
  } | null;
}

export interface Today {
  offerings: TodayOffering[];
  mastery: Mastery[];
  suggestion: {
    kind: 'REVIEW' | 'KEEP_GOING';
    competency_id: string | null;
    title: string | null;
  } | null;
}

export interface LessonSummary {
  id: string;
  offering_id: string;
  module_id: string | null;
  title_fa: string;
  est_minutes: number;
  publish_at: string | null;
  updated_at: string;
}

export interface LessonDetail extends LessonSummary {
  body_md: string;
  checkpoints: {
    quiz_id: string;
    title_fa: string;
    opens_at: string;
    closes_at: string;
    duration_min: number;
    status: string;
  }[];
}

export interface StaffLesson {
  id: string;
  offering_id: string;
  module_id: string | null;
  week_id: string | null;
  title_fa: string;
  body_md: string;
  est_minutes: number;
  status: 'DRAFT' | 'PUBLISHED';
  publish_at: string | null;
  sort_order: number;
  updated_at: string;
}

export interface Concept {
  id: string;
  code: string;
  title_fa: string;
}

export interface Competency {
  id: string;
  code: string;
  title_fa: string;
  domain: string | null;
  concepts: Concept[];
}

export function fetchToday(token: string) {
  return apiFetch<Today>('/learning/today', { accessToken: token });
}

export function fetchStudentLessons(offeringId: string, token: string) {
  return apiFetch<LessonSummary[]>(`/learning/offerings/${offeringId}/lessons`, {
    accessToken: token,
  });
}

export function fetchLesson(lessonId: string, token: string) {
  return apiFetch<LessonDetail>(`/learning/lessons/${lessonId}`, { accessToken: token });
}

// ── کادر ───────────────────────────────────────────────────────────────
export function fetchStaffLessons(offeringId: string, token: string) {
  return apiFetch<StaffLesson[]>(`/learning/teach/offerings/${offeringId}/lessons`, {
    accessToken: token,
  });
}

export interface LessonInput {
  title_fa: string;
  body_md: string;
  est_minutes: number;
  publish_at: string | null;
}

export function createLesson(
  offeringId: string,
  input: LessonInput & { publish: boolean },
  token: string,
) {
  return apiFetch<StaffLesson>(`/learning/teach/offerings/${offeringId}/lessons`, {
    method: 'POST',
    body: input,
    accessToken: token,
  });
}

export function updateLesson(
  offeringId: string,
  lessonId: string,
  input: LessonInput,
  token: string,
) {
  return apiFetch<StaffLesson>(`/learning/teach/offerings/${offeringId}/lessons/${lessonId}`, {
    method: 'PUT',
    body: input,
    accessToken: token,
  });
}

export function setLessonPublished(
  offeringId: string,
  lessonId: string,
  published: boolean,
  token: string,
) {
  return apiFetch<StaffLesson>(
    `/learning/teach/offerings/${offeringId}/lessons/${lessonId}/publish`,
    { method: 'POST', body: { published }, accessToken: token },
  );
}

export function deleteLesson(offeringId: string, lessonId: string, token: string) {
  return apiFetch<void>(`/learning/teach/offerings/${offeringId}/lessons/${lessonId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

export function fetchCompetencies(token: string) {
  return apiFetch<Competency[]>('/learning/competencies', { accessToken: token });
}

export function createCompetency(input: { code: string; title_fa: string }, token: string) {
  return apiFetch<Competency>('/learning/competencies', {
    method: 'POST',
    body: input,
    accessToken: token,
  });
}

export function createConcept(
  competencyId: string,
  input: { code: string; title_fa: string },
  token: string,
) {
  return apiFetch<Concept>(`/learning/competencies/${competencyId}/concepts`, {
    method: 'POST',
    body: input,
    accessToken: token,
  });
}

export interface CheckpointInput {
  title_fa: string;
  lesson_id: string | null;
  concept_ids: string[];
  draw_count: number;
  opens_at: string;
  closes_at: string;
  duration_min: number;
  publish: boolean;
}

export function createCheckpoint(offeringId: string, input: CheckpointInput, token: string) {
  return apiFetch<{
    id: string;
    title_fa: string;
    status: string;
    draw_count: number | null;
    pool_size: number;
  }>(`/learning/teach/offerings/${offeringId}/checkpoints`, {
    method: 'POST',
    body: input,
    accessToken: token,
  });
}
