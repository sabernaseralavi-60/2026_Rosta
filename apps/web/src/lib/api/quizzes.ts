/** فراخوان‌های /quizzes و /attempts — قرارداد §5.6. */

import { apiFetch } from './client';

export type QuestionKind =
  | 'SINGLE_CHOICE'
  | 'MULTI_CHOICE'
  | 'TRUE_FALSE'
  | 'SHORT_ANSWER'
  | 'NUMERIC'
  | 'ESSAY'
  | 'MATCHING';

export type QuizAvailability =
  | 'NOT_OPEN'
  | 'AVAILABLE'
  | 'IN_PROGRESS'
  | 'EXHAUSTED'
  | 'CLOSED';

export type AttemptStatus =
  | 'IN_PROGRESS'
  | 'SUBMITTED'
  | 'AUTO_SUBMITTED'
  | 'GRADED'
  | 'VOIDED';

export type AppealStatus = 'OPEN' | 'ACCEPTED' | 'REJECTED';
export type IntegrityEventKind = 'TAB_BLUR' | 'WINDOW_RESIZE' | 'LONG_PASTE' | 'RECONNECT';

/**
 * پاسخ دانشجو به یک سؤال.
 *
 * شکلش به نوع سؤال بستگی دارد و همان چیزی است که سرور در
 * `quiz_answers.response` ذخیره می‌کند:
 *
 *   چندگزینه‌ای  `{ selected: ['a'] }`
 *   درست/نادرست  `{ value: true }`
 *   کوتاه/تشریحی `{ text: '…' }`
 *   عددی         `{ value: '12.5' }`
 *   جورکردنی     `{ pairs: [['l1', 'r1']] }`
 */
export type AnswerResponse =
  | { selected: string[] }
  | { value: boolean | string | number }
  | { text: string }
  | { pairs: [string, string][] };

export interface QuizSummary {
  id: string;
  title_fa: string;
  description: string | null;
  week_number: number | null;
  duration_min: number;
  opens_at: string;
  closes_at: string;
  max_attempts: number;
  total_points: string;
  question_count: number;
  passing_score: string | null;
  /** وضعیت و متنش هر دو از سرور می‌آیند — §5.6. */
  state: QuizAvailability;
  state_fa: string;
  server_time: string;
  used_attempts: number;
  active_attempt_id: string | null;
  /**
   * وقت واقعیِ باقی‌مانده اگر همین حالا شروع کند. ممکن است از
   * `duration_min` کمتر باشد چون `expires_at` از `closes_at` جلو
   * نمی‌زند (ADR-0011).
   */
  effective_duration_sec: number | null;
}

export interface AttemptStart {
  attempt_id: string;
  server_time: string;
  expires_at: string;
  seconds_remaining: number;
  question_count: number;
  total_points: string;
}

export interface VisibleQuestion {
  id: string;
  kind: QuestionKind;
  kind_fa: string;
  body: string;
  points: string;
  /** هرگز کلید پاسخ ندارد — الزام امنیتی §5.6. */
  payload: Record<string, unknown>;
  my_answer: AnswerResponse | null;
  is_flagged: boolean;
}

export interface AttemptView {
  attempt_id: string;
  quiz_id: string;
  quiz_title_fa: string;
  status: AttemptStatus;
  server_time: string;
  expires_at: string;
  seconds_remaining: number;
  total_points: string;
  questions: VisibleQuestion[];
}

export interface SaveAnswerResult {
  saved_at: string;
  seconds_remaining: number;
}

export interface SyncResult {
  accepted: string[];
  rejected: string[];
  seconds_remaining: number;
}

export interface SubmitResult {
  status: AttemptStatus;
  auto_score: string;
  is_provisional: boolean;
  total_points: string;
  result_available: boolean;
}

export interface QuestionReview {
  correct: unknown;
  accepted: string[] | null;
  tolerance: string | null;
  explanation: string | null;
}

export interface ResultQuestion {
  id: string;
  kind: QuestionKind;
  kind_fa: string;
  body: string;
  points: string;
  score: string | null;
  is_correct: boolean | null;
  my_answer: AnswerResponse | null;
  feedback: string | null;
  review: QuestionReview | null;
}

export interface AttemptResult {
  attempt_id: string;
  quiz_id: string;
  quiz_title_fa: string;
  attempt_no: number;
  status: AttemptStatus;
  submitted_at: string | null;
  total_score: string | null;
  total_points: string;
  is_provisional: boolean;
  /** «زمانت تمام شد» با «ارسال کردی» یکی نیست — ADR-0011. */
  auto_closed: boolean;
  passed: boolean | null;
  /** زیر آستانهٔ حریم خصوصی `null` می‌ماند. */
  class_average: string | null;
  cohort_size: number;
  questions: ResultQuestion[];
}

export interface Appeal {
  id: string;
  attempt_id: string;
  question_id: string | null;
  status: AppealStatus;
  status_fa: string;
  reason: string;
  response: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface OfflineAnswer {
  question_id: string;
  response: AnswerResponse | null;
  is_flagged: boolean;
  client_ts: string;
}

// ── خواندن ────────────────────────────────────────────────────────────
export function fetchOfferingQuizzes(offeringId: string, accessToken: string) {
  return apiFetch<QuizSummary[]>(`/quizzes/offering/${offeringId}`, { accessToken });
}

export function fetchQuiz(quizId: string, accessToken: string) {
  return apiFetch<QuizSummary>(`/quizzes/${quizId}`, { accessToken });
}

export function fetchAttempt(attemptId: string, accessToken: string) {
  return apiFetch<AttemptView>(`/attempts/${attemptId}`, { accessToken });
}

export function fetchResult(attemptId: string, accessToken: string) {
  return apiFetch<AttemptResult>(`/attempts/${attemptId}/result`, { accessToken });
}

// ── نوشتن ─────────────────────────────────────────────────────────────
export function startAttempt(quizId: string, accessToken: string) {
  return apiFetch<AttemptStart>(`/quizzes/${quizId}/attempts`, {
    method: 'POST',
    accessToken,
  });
}

export function saveAnswer(
  attemptId: string,
  questionId: string,
  body: { response: AnswerResponse | null; is_flagged?: boolean; client_ts?: string },
  accessToken: string,
) {
  return apiFetch<SaveAnswerResult>(`/attempts/${attemptId}/answers/${questionId}`, {
    method: 'PUT',
    accessToken,
    body,
  });
}

/**
 * همگام‌سازی دسته‌ای پس از آفلاین — §5.6.
 *
 * `client_ts` هر پاسخ لحظه‌ای است که دانشجو **نوشت**، نه لحظهٔ ارسال.
 * سرور با همین تصمیم می‌گیرد پاسخِ دیررسیده را بپذیرد یا نه.
 */
export function syncAnswers(
  attemptId: string,
  answers: OfflineAnswer[],
  accessToken: string,
) {
  return apiFetch<SyncResult>(`/attempts/${attemptId}/sync`, {
    method: 'POST',
    accessToken,
    body: { answers },
  });
}

export function submitAttempt(
  attemptId: string,
  confirmUnanswered: number,
  accessToken: string,
) {
  return apiFetch<SubmitResult>(`/attempts/${attemptId}/submit`, {
    method: 'POST',
    accessToken,
    body: { confirm_unanswered: confirmUnanswered },
  });
}

export function recordIntegrityEvent(
  attemptId: string,
  kind: IntegrityEventKind,
  accessToken: string,
  detail?: Record<string, unknown>,
) {
  return apiFetch<{ recorded: number }>(`/attempts/${attemptId}/integrity`, {
    method: 'POST',
    accessToken,
    body: { kind, detail: detail ?? null },
  });
}

export function openAppeal(
  attemptId: string,
  body: { reason: string; question_id?: string | null },
  accessToken: string,
) {
  return apiFetch<Appeal>(`/attempts/${attemptId}/appeal`, {
    method: 'POST',
    accessToken,
    body,
  });
}
