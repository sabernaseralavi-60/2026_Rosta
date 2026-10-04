/**
 * ناحیهٔ استاد — §3.5، §5.11، ADR-0019.
 *
 * همهٔ مسیرهای `/teach`: ارائه و هفته و منبع (M3)، آزمون و تصحیح (M4)،
 * داشبورد استثنامحور و نمرهٔ یادگیری (M5)، و آنچه ADR-0019 افزود — نمای
 * کادر آموزشی از ارائه، تنظیمات، خواندن حضور و دفتر نمره.
 *
 * سرور هر مسیر را با قلمرو ارائه می‌سنجد؛ `permissions` در نمای ارائه فقط
 * برای پنهان کردن دکمه‌ای است که کار نمی‌کند، نه برای امنیت.
 */

import { apiFetch } from './client';
import type { Announcement, EnrollmentStatus, ResourceKind, WeekSummary } from './courses';
import type { ProjectKind } from './projects';
import type { Appeal, AttemptResult, AttemptStatus, QuestionKind } from './quizzes';
import type { DeliverableStatus } from './workspace';

// ── ارائه ─────────────────────────────────────────────────────────────
export type OfferingStatus = 'DRAFT' | 'OPEN' | 'IN_PROGRESS' | 'CLOSED' | 'ARCHIVED';
export type StaffRole = 'INSTRUCTOR' | 'TA' | 'COORDINATOR' | 'ADMIN';

export const OFFERING_STATUS_LABELS: Record<OfferingStatus, string> = {
  DRAFT: 'پیش‌نویس',
  OPEN: 'باز برای ثبت‌نام',
  IN_PROGRESS: 'در حال برگزاری',
  CLOSED: 'پایان‌یافته',
  ARCHIVED: 'بایگانی',
};

export const STAFF_ROLE_LABELS: Record<StaffRole, string> = {
  INSTRUCTOR: 'استاد',
  TA: 'دستیار آموزشی',
  COORDINATOR: 'مدیر آموزشی',
  ADMIN: 'مدیر سامانه',
};

/** نقش‌هایی که پیوند «تدریس» را در هدر می‌بینند. سرور هر مسیر را جدا می‌سنجد. */
export const TEACH_AREA_ROLES = ['INSTRUCTOR', 'TA', 'COORDINATOR'];

export function canSeeTeach(roles: string[] | undefined | null): boolean {
  return (roles ?? []).some((role) => TEACH_AREA_ROLES.includes(role));
}

export interface TeachOffering {
  id: string;
  course_id: string;
  course_slug: string;
  course_title_fa: string;
  term_code: string;
  term_title_fa: string;
  instructor_id: string;
  instructor_name: string | null;
  status: OfferingStatus;
  requires_approval: boolean;
  has_enrollment_code: boolean;
  capacity: number | null;
  active_students: number;
  staff_role: StaffRole | null;
  pending_enrollments: number;
}

export interface OfferingPermissions {
  manage: boolean;
  edit_weeks: boolean;
  publish_weeks: boolean;
  upload_resources: boolean;
  record_attendance: boolean;
  approve_enrollments: boolean;
  submit_final_grades: boolean;
  publish_announcements: boolean;
  create_quizzes: boolean;
  grade_quizzes: boolean;
}

export interface TeachOfferingDetail extends TeachOffering {
  enrollment_code: string | null;
  grading_policy: Partial<Record<GradingKey, number>>;
  weeks: WeekSummary[];
  announcements: TeachAnnouncement[];
  quiz_count: number;
  allowed_statuses: OfferingStatus[];
  permissions: OfferingPermissions;
}

export interface OfferingSettings {
  status?: OfferingStatus;
  requires_approval?: boolean;
  capacity?: number;
  enrollment_code?: string;
  clear_capacity?: boolean;
  clear_enrollment_code?: boolean;
}

export type GradingKey = 'quiz' | 'project' | 'attendance' | 'participation';

export const GRADING_LABELS: Record<GradingKey, string> = {
  quiz: 'آزمون‌ها',
  project: 'پروژه',
  attendance: 'حضور',
  participation: 'مشارکت',
};

export function fetchTeachOfferings(token: string) {
  return apiFetch<TeachOffering[]>('/teach/offerings', { accessToken: token });
}

export function fetchTeachOffering(offeringId: string, token: string) {
  return apiFetch<TeachOfferingDetail>(`/teach/offerings/${offeringId}`, { accessToken: token });
}

export function updateOffering(offeringId: string, body: OfferingSettings, token: string) {
  return apiFetch<TeachOfferingDetail>(`/teach/offerings/${offeringId}`, {
    method: 'PATCH',
    body,
    accessToken: token,
  });
}

export function setGradingPolicy(
  offeringId: string,
  policy: Record<GradingKey, number>,
  token: string,
) {
  return apiFetch<Record<string, number>>(`/teach/offerings/${offeringId}/grading-policy`, {
    method: 'PUT',
    body: policy,
    accessToken: token,
  });
}

export function copyContent(offeringId: string, sourceOfferingId: string, token: string) {
  return apiFetch<{ weeks_copied: number }>(`/teach/offerings/${offeringId}/copy-content`, {
    method: 'POST',
    body: { source_offering_id: sourceOfferingId },
    accessToken: token,
  });
}

// ── هفته و منبع ───────────────────────────────────────────────────────
export interface WeekInput {
  week_number: number;
  title_fa: string;
  description?: string | null;
  objectives?: string[] | null;
  publish_at?: string | null;
}

export function saveWeek(offeringId: string, body: WeekInput, token: string) {
  return apiFetch<WeekSummary>(`/teach/offerings/${offeringId}/weeks`, {
    method: 'PUT',
    body,
    accessToken: token,
  });
}

/** `publishAt` خالی یعنی «همین حالا»؛ تاریخ آینده یعنی زمان‌بندی. */
export function publishWeek(weekId: string, publishAt: string | null, token: string) {
  return apiFetch<WeekSummary>(`/teach/weeks/${weekId}/publish`, {
    method: 'POST',
    body: { publish_at: publishAt },
    accessToken: token,
  });
}

export interface ResourceInput {
  kind: ResourceKind;
  title_fa: string;
  description?: string | null;
  file_id?: string | null;
  external_url?: string | null;
  duration_sec?: number | null;
  is_downloadable?: boolean;
  is_required?: boolean;
}

export const RESOURCE_KIND_LABELS: Record<ResourceKind, string> = {
  PDF: 'جزوه (PDF)',
  VIDEO: 'ویدئو',
  LINK: 'پیوند',
  SLIDE: 'اسلاید',
  DATASET: 'داده',
  CODE: 'کد',
  OTHER: 'سایر',
};

export function addResource(
  offeringId: string,
  weekId: string,
  body: ResourceInput,
  token: string,
) {
  return apiFetch<{ id: string }>(`/teach/offerings/${offeringId}/weeks/${weekId}/resources`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

export function removeResource(resourceId: string, token: string) {
  return apiFetch<void>(`/teach/resources/${resourceId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

export function linkMaterial(
  offeringId: string,
  weekId: string,
  materialId: string,
  token: string,
  isRequired = true,
) {
  return apiFetch<void>(`/teach/offerings/${offeringId}/weeks/${weekId}/materials`, {
    method: 'POST',
    body: { material_id: materialId, is_required: isRequired },
    accessToken: token,
  });
}

export function unlinkMaterial(
  offeringId: string,
  weekId: string,
  materialId: string,
  token: string,
) {
  return apiFetch<void>(`/teach/offerings/${offeringId}/weeks/${weekId}/materials/${materialId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

// ── دانشجویان ─────────────────────────────────────────────────────────
export interface RosterEntry {
  enrollment_id: string;
  student_id: string;
  student_name: string | null;
  status: EnrollmentStatus;
  final_grade: number | null;
  enrolled_at: string;
}

export const ENROLLMENT_STATUS_LABELS: Record<EnrollmentStatus, string> = {
  PENDING: 'در انتظار تأیید',
  ACTIVE: 'فعال',
  DROPPED: 'انصراف',
  COMPLETED: 'نمره گرفته',
  REJECTED: 'ردشده',
};

export function fetchRoster(offeringId: string, token: string) {
  return apiFetch<RosterEntry[]>(`/teach/offerings/${offeringId}/students`, {
    accessToken: token,
  });
}

export function decideEnrollment(enrollmentId: string, approve: boolean, token: string) {
  return apiFetch<{ id: string; status: EnrollmentStatus }>(
    `/teach/enrollments/${enrollmentId}/decide`,
    { method: 'POST', body: { approve }, accessToken: token },
  );
}

export function setFinalGrade(enrollmentId: string, grade: number, token: string) {
  return apiFetch<{ id: string; status: EnrollmentStatus; final_grade: number | null }>(
    `/teach/enrollments/${enrollmentId}/grade`,
    { method: 'PATCH', body: { grade }, accessToken: token },
  );
}

// ── حضور و غیاب ───────────────────────────────────────────────────────
export type AttendanceStatus = 'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED';

export const ATTENDANCE_LABELS: Record<AttendanceStatus, string> = {
  PRESENT: 'حاضر',
  LATE: 'تأخیر',
  ABSENT: 'غایب',
  EXCUSED: 'موجه',
};

export interface AttendanceSession {
  held_on: string;
  week_number: number | null;
  topic: string | null;
  present: number;
  late: number;
  absent: number;
  excused: number;
}

export interface AttendanceSheet extends AttendanceSession {
  marks: { student_id: string; status: AttendanceStatus; note: string | null }[];
}

export interface AttendanceInput {
  held_on: string;
  week_number?: number | null;
  topic?: string | null;
  entries: { student_id: string; status: AttendanceStatus; note?: string | null }[];
}

export function fetchAttendanceSessions(offeringId: string, token: string) {
  return apiFetch<AttendanceSession[]>(`/teach/offerings/${offeringId}/attendance`, {
    accessToken: token,
  });
}

export function fetchAttendanceSheet(offeringId: string, heldOn: string, token: string) {
  return apiFetch<AttendanceSheet>(`/teach/offerings/${offeringId}/attendance/${heldOn}`, {
    accessToken: token,
  });
}

export function recordAttendance(offeringId: string, body: AttendanceInput, token: string) {
  return apiFetch<{ recorded: number }>(`/teach/offerings/${offeringId}/attendance`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

// ── دفتر نمره — §3.5، §9.6 ────────────────────────────────────────────
export interface LearningComponent {
  key: 'quiz' | 'study' | 'project' | 'attendance';
  title_fa: string;
  ratio: string | null;
  weight: string;
  earned: string;
  possible: string;
}

export interface GradebookQuiz {
  id: string;
  title_fa: string;
  status: string;
  total_points: string;
  closes_at: string;
}

export interface GradebookRow {
  enrollment_id: string;
  student_id: string;
  student_name: string | null;
  status: EnrollmentStatus;
  quizzes: { quiz_id: string; score: string | null; is_provisional: boolean; attempts: number }[];
  attendance: { present: number; late: number; absent: number; excused: number };
  learning_score: string | null;
  suggested_grade: string | null;
  components: LearningComponent[];
  final_grade: number | null;
}

export interface Gradebook {
  offering_id: string;
  sessions_held: number;
  quizzes: GradebookQuiz[];
  rows: GradebookRow[];
}

export function fetchGradebook(offeringId: string, token: string) {
  return apiFetch<Gradebook>(`/teach/offerings/${offeringId}/gradebook`, { accessToken: token });
}

// ── اعلان درس ─────────────────────────────────────────────────────────
export interface AnnouncementInput {
  title: string;
  body: string;
  priority: Announcement['priority'];
  expires_at?: string | null;
}

export const PRIORITY_LABELS: Record<Announcement['priority'], string> = {
  NORMAL: 'عادی',
  IMPORTANT: 'مهم',
  URGENT: 'فوری — پیامک هم می‌رود',
};

export function publishAnnouncement(offeringId: string, body: AnnouncementInput, token: string) {
  return apiFetch<Announcement>(`/teach/offerings/${offeringId}/announcements`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

/** نویسندهٔ اعلان، یا استاد درس — آینهٔ قاعدهٔ سرور (ADR-0021). */
export interface TeachAnnouncement extends Announcement {
  can_edit: boolean;
}

/** اهمیت پس از انتشار عوض نمی‌شود؛ ویرایش دوباره نمی‌فرستد. */
export interface AnnouncementPatch {
  title?: string;
  body?: string;
  expires_at?: string | null;
}

export function reviseAnnouncement(
  offeringId: string,
  announcementId: string,
  body: AnnouncementPatch,
  token: string,
) {
  return apiFetch<Announcement>(`/teach/offerings/${offeringId}/announcements/${announcementId}`, {
    method: 'PATCH',
    body,
    accessToken: token,
  });
}

export function deleteAnnouncement(offeringId: string, announcementId: string, token: string) {
  return apiFetch<void>(`/teach/offerings/${offeringId}/announcements/${announcementId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

// ── داشبورد استثنامحور — FR-DASH-02 ───────────────────────────────────
export interface Queue {
  count: number;
  oldest_days: number | null;
}

export interface TeachDashboard {
  needs_attention: {
    deliverables_pending: Queue;
    essays_pending: Queue;
    enrollment_requests: Queue;
    grade_appeals: Queue;
    projects_at_risk: {
      id: string;
      title_fa: string;
      health: string;
      health_fa: string;
      days_inactive: number;
    }[];
    students_at_risk: {
      user_id: string;
      display_name: string | null;
      reason: string;
      offering_id: string;
      course_title_fa: string;
    }[];
  };
  offerings: {
    id: string;
    title_fa: string;
    status: string;
    students: number;
    avg_progress: string | null;
    avg_quiz_score: string | null;
    avg_learning_score: string | null;
  }[];
}

export function fetchTeachDashboard(token: string) {
  return apiFetch<TeachDashboard>('/teach/dashboard', { accessToken: token });
}

// ── آزمون — M4 ────────────────────────────────────────────────────────
export type QuizStatus = 'DRAFT' | 'PUBLISHED' | 'CLOSED';
export type ResultVisibility = 'IMMEDIATE' | 'AFTER_CLOSE' | 'MANUAL';

export const RESULT_VISIBILITY_LABELS: Record<ResultVisibility, string> = {
  IMMEDIATE: 'بلافاصله پس از ارسال',
  AFTER_CLOSE: 'پس از پایان مهلت',
  MANUAL: 'وقتی خودم منتشر کنم',
};

/** عنوان هفت نوع سؤال — FR-QUIZ-01؛ همان `QUESTION_KIND_TITLE_FA` سرور. */
export const KIND_LABELS: Record<QuestionKind, string> = {
  SINGLE_CHOICE: 'چندگزینه‌ای — یک پاسخ',
  MULTI_CHOICE: 'چندگزینه‌ای — چند پاسخ',
  TRUE_FALSE: 'درست/نادرست',
  SHORT_ANSWER: 'پاسخ کوتاه',
  NUMERIC: 'عددی',
  ESSAY: 'تشریحی',
  MATCHING: 'جورکردنی',
};

export interface TeachQuestion {
  id: string;
  kind: QuestionKind;
  kind_fa: string;
  body: string;
  payload: Record<string, unknown>;
  explanation: string | null;
  points: string;
  sort_order: number;
  bank_id: string | null;
}

export interface TeachQuiz {
  id: string;
  offering_id: string;
  week_id: string | null;
  title_fa: string;
  description: string | null;
  duration_min: number;
  opens_at: string;
  closes_at: string;
  max_attempts: number;
  passing_score: string | null;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  result_visibility: ResultVisibility;
  result_visibility_fa: string;
  show_correct_answers: boolean;
  status: QuizStatus;
  status_fa: string;
  total_points: string;
  results_published_at: string | null;
  attempt_count: number;
  questions: TeachQuestion[];
}

export interface QuizInput {
  title_fa: string;
  duration_min: number;
  opens_at: string;
  closes_at: string;
  week_id?: string | null;
  description?: string | null;
  max_attempts: number;
  passing_score?: string | null;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  result_visibility: ResultVisibility;
  show_correct_answers: boolean;
}

export interface QuestionInput {
  kind: QuestionKind;
  body: string;
  payload: Record<string, unknown>;
  points: string;
  explanation?: string | null;
}

export function fetchOfferingQuizzesForStaff(offeringId: string, token: string) {
  return apiFetch<TeachQuiz[]>(`/teach/offerings/${offeringId}/quizzes`, { accessToken: token });
}

export function createQuiz(offeringId: string, body: QuizInput, token: string) {
  return apiFetch<TeachQuiz>(`/teach/offerings/${offeringId}/quizzes`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

export function fetchTeachQuiz(quizId: string, token: string) {
  return apiFetch<TeachQuiz>(`/teach/quizzes/${quizId}`, { accessToken: token });
}

export function updateQuiz(quizId: string, body: QuizInput, token: string) {
  return apiFetch<TeachQuiz>(`/teach/quizzes/${quizId}`, {
    method: 'PUT',
    body,
    accessToken: token,
  });
}

export function quizAction(
  quizId: string,
  action: 'publish' | 'close' | 'publish-results',
  token: string,
) {
  return apiFetch<TeachQuiz>(`/teach/quizzes/${quizId}/${action}`, {
    method: 'POST',
    accessToken: token,
  });
}

export function deleteQuiz(quizId: string, token: string) {
  return apiFetch<void>(`/teach/quizzes/${quizId}`, { method: 'DELETE', accessToken: token });
}

export function addQuestion(quizId: string, body: QuestionInput, token: string) {
  return apiFetch<TeachQuestion>(`/teach/quizzes/${quizId}/questions`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

export function updateQuestion(
  quizId: string,
  questionId: string,
  body: QuestionInput,
  token: string,
) {
  return apiFetch<TeachQuestion>(`/teach/quizzes/${quizId}/questions/${questionId}`, {
    method: 'PUT',
    body,
    accessToken: token,
  });
}

export function deleteQuestion(quizId: string, questionId: string, token: string) {
  return apiFetch<void>(`/teach/quizzes/${quizId}/questions/${questionId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

export function reorderQuestions(quizId: string, questionIds: string[], token: string) {
  return apiFetch<TeachQuestion[]>(`/teach/quizzes/${quizId}/questions/reorder`, {
    method: 'POST',
    body: { question_ids: questionIds },
    accessToken: token,
  });
}

// ── بانک سؤال — M4-03 ─────────────────────────────────────────────────
export interface BankItem {
  id: string;
  kind: QuestionKind;
  kind_fa: string;
  body: string;
  payload: Record<string, unknown>;
  explanation: string | null;
  course_id: string | null;
  category: string | null;
  difficulty: number | null;
  concept_id: string | null;
  usage_count: number;
}

export interface BankFilters {
  course_id?: string;
  category?: string;
  difficulty?: number;
  kind?: QuestionKind;
}

export function fetchBank(filters: BankFilters, token: string) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return apiFetch<BankItem[]>(`/teach/question-bank${query ? `?${query}` : ''}`, {
    accessToken: token,
  });
}

export type BankItemInput = Omit<QuestionInput, 'points'> & {
  course_id?: string | null;
  category?: string | null;
  difficulty?: number | null;
  concept_id?: string | null;
};

export function addBankItem(body: BankItemInput, token: string) {
  return apiFetch<BankItem>('/teach/question-bank', { method: 'POST', body, accessToken: token });
}

/** جایگزینی کامل — آزمون‌ها کپی دارند و عوض نمی‌شوند (ADR-0021). */
export function updateBankItem(id: string, body: BankItemInput, token: string) {
  return apiFetch<BankItem>(`/teach/question-bank/${id}`, {
    method: 'PUT',
    body,
    accessToken: token,
  });
}

export function deleteBankItem(id: string, token: string) {
  return apiFetch<void>(`/teach/question-bank/${id}`, { method: 'DELETE', accessToken: token });
}

export function copyFromBank(quizId: string, bankIds: string[], points: string, token: string) {
  return apiFetch<TeachQuestion[]>(`/teach/quizzes/${quizId}/questions/from-bank`, {
    method: 'POST',
    body: { bank_ids: bankIds, points },
    accessToken: token,
  });
}

export function pickRandom(
  quizId: string,
  body: {
    count: number;
    course_id?: string;
    category?: string;
    difficulty?: number;
    points: string;
  },
  token: string,
) {
  return apiFetch<TeachQuestion[]>(`/teach/quizzes/${quizId}/questions/random`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

// ── تلاش‌ها، تصحیح و اعتراض ──────────────────────────────────────────
export interface AttemptSummary {
  id: string;
  student_id: string;
  student_name: string;
  attempt_no: number;
  status: AttemptStatus;
  status_fa: string;
  submitted_at: string | null;
  total_score: string | null;
  is_provisional: boolean;
  auto_closed: boolean;
  integrity_event_count: number;
}

export interface PendingAnswer {
  attempt_id: string;
  question_id: string;
  student_name: string;
  attempt_no: number;
  response: { text?: string } | null;
  points: string;
}

export interface GradingQueue {
  question_id: string;
  body: string;
  points: string;
  rubric: string | null;
  graded_count: number;
  pending: PendingAnswer[];
}

export interface OptionStat {
  option_id: string;
  text: string;
  is_correct: boolean;
  chosen: number;
  share: number;
  top_share: number | null;
  bottom_share: number | null;
  note_fa: string | null;
}

export interface ItemAnalysis {
  question_id: string;
  body: string;
  kind: QuestionKind;
  points: string;
  answered: number;
  difficulty: string | null;
  discrimination: string | null;
  item_rest: number | null;
  note_fa: string | null;
  options: OptionStat[];
}

export interface ScoreSummary {
  n: number;
  mean_percent: number;
  median_percent: number;
  sd_percent: number | null;
  min_percent: number;
  max_percent: number;
  histogram: number[];
}

export interface Reliability {
  alpha: number;
  sem_percent: number;
  label_fa: string;
  advice_fa: string | null;
}

export interface QuizAnalytics {
  summary: ScoreSummary | null;
  reliability: Reliability | null;
  items: ItemAnalysis[];
}

export function fetchAttempts(quizId: string, token: string) {
  return apiFetch<AttemptSummary[]>(`/teach/quizzes/${quizId}/attempts`, { accessToken: token });
}

export function fetchGradingQueue(quizId: string, token: string) {
  return apiFetch<GradingQueue[]>(`/teach/quizzes/${quizId}/grading-queue`, {
    accessToken: token,
  });
}

export function gradeAnswer(
  quizId: string,
  attemptId: string,
  questionId: string,
  body: { score: string; feedback?: string | null },
  token: string,
) {
  return apiFetch<{
    score: string;
    attempt_total: string | null;
    attempt_is_provisional: boolean;
  }>(`/teach/quizzes/${quizId}/attempts/${attemptId}/answers/${questionId}`, {
    method: 'PUT',
    body,
    accessToken: token,
  });
}

export function attemptAction(
  quizId: string,
  attemptId: string,
  action: 'finalize' | 'void',
  token: string,
) {
  return apiFetch<AttemptSummary>(`/teach/quizzes/${quizId}/attempts/${attemptId}/${action}`, {
    method: 'POST',
    accessToken: token,
  });
}

export function fetchStaffResult(quizId: string, attemptId: string, token: string) {
  return apiFetch<AttemptResult>(`/teach/quizzes/${quizId}/attempts/${attemptId}/result`, {
    accessToken: token,
  });
}

export function fetchQuizAnalytics(quizId: string, token: string) {
  return apiFetch<QuizAnalytics>(`/teach/quizzes/${quizId}/analytics`, {
    accessToken: token,
  });
}

export function fetchQuizAppeals(quizId: string, token: string, onlyOpen = true) {
  return apiFetch<Appeal[]>(`/teach/quizzes/${quizId}/appeals?only_open=${onlyOpen}`, {
    accessToken: token,
  });
}

export function resolveAppeal(
  appealId: string,
  body: { accept: boolean; response: string; new_score?: string | null },
  token: string,
) {
  return apiFetch<Appeal>(`/teach/appeals/${appealId}/resolve`, {
    method: 'POST',
    body,
    accessToken: token,
  });
}

// ── پروژه‌های تحت نظارت و صف بررسی — ADR-0022 ─────────────────────────
export type ProjectHealth = 'HEALTHY' | 'AT_RISK' | 'STALLED';
export type SupervisedProjectStatus =
  'DRAFT' | 'OPEN' | 'IN_PROGRESS' | 'PAUSED' | 'COMPLETED' | 'CANCELLED';

export const SUPERVISED_STATUS_LABELS: Record<SupervisedProjectStatus, string> = {
  DRAFT: 'پیش‌نویس',
  OPEN: 'باز برای عضو',
  IN_PROGRESS: 'در جریان',
  PAUSED: 'متوقف‌شده موقت',
  COMPLETED: 'تمام‌شده',
  CANCELLED: 'لغو‌شده',
};

export interface TeachProject {
  id: string;
  title_fa: string;
  kind: ProjectKind;
  kind_fa: string;
  status: SupervisedProjectStatus;
  health: ProjectHealth;
  health_fa: string;
  offering_id: string | null;
  /** درس ارائه‌ای که پروژه به آن وصل است؛ `null` برای پروژه‌ای که خود استاد مدیرش است. */
  course_title_fa: string | null;
  lead_id: string;
  lead_name: string | null;
  active_members: number;
  team_size_max: number;
  milestones_total: number;
  milestones_approved: number;
  milestones_overdue: number;
  open_deliverables: number;
  oldest_open_days: number | null;
  days_inactive: number;
  deadline_on: string | null;
}

export interface ReviewQueueItem {
  deliverable_id: string;
  project_id: string;
  project_title_fa: string;
  course_title_fa: string | null;
  milestone_id: string;
  milestone_title_fa: string;
  submitter_id: string;
  submitter_name: string | null;
  version: number;
  status: DeliverableStatus;
  status_fa: string;
  is_late: boolean;
  submitted_at: string;
  days_waiting: number;
  excerpt: string | null;
  link_count: number;
}

export interface ReviewQueue {
  /** شمار کل؛ اگر از `items.length` بیشتر بود، فهرست بریده شده است. */
  total: number;
  oldest_days: number | null;
  items: ReviewQueueItem[];
}

export function fetchTeachProjects(token: string) {
  return apiFetch<TeachProject[]>('/teach/projects', { accessToken: token });
}

export function fetchReviewQueue(token: string) {
  return apiFetch<ReviewQueue>('/teach/review-queue', { accessToken: token });
}
