/**
 * فراخوان‌های فضای کاری پروژه — §5.7، M2.
 *
 * ساخت و ویرایش پروژه، درخواست پیوستن، تیم، مرحله، تحویل‌دادنی، تختهٔ
 * وظایف، گفتگو و جریان فعالیت.
 *
 * متن‌های فارسیِ وضعیت (`status_fa`، `kind_fa`، …) از **سرور** می‌آیند و
 * اینجا بازسازی نمی‌شوند — همان قاعده‌ای که برای دلیل تطابق (§8.10)
 * برقرار است: منطق نمایش در یک جا می‌ماند.
 */

import { apiFetch } from './client';
import type { ProjectDetail, ProjectKind, ProjectSummary, Reason, WorkStyle } from './projects';

export type ProjectStatus =
  | 'DRAFT'
  | 'OPEN'
  | 'IN_PROGRESS'
  | 'PAUSED'
  | 'COMPLETED'
  | 'CANCELLED';

export type ApplicationStatus =
  | 'PENDING'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'WAITLISTED'
  | 'WITHDRAWN';

export type ApplicationDecision = 'ACCEPTED' | 'REJECTED' | 'WAITLISTED';
export type MilestoneStatus = 'PENDING' | 'IN_PROGRESS' | 'SUBMITTED' | 'APPROVED' | 'OVERDUE';
export type DeliverableStatus =
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'CHANGES_REQUESTED'
  | 'REJECTED';
export type ReviewDecision = 'APPROVED' | 'CHANGES_REQUESTED' | 'REJECTED';
export type TaskStatus = 'TODO' | 'DOING' | 'DONE';
export type OutputKind = 'DOCUMENT' | 'CODE' | 'DATA' | 'MEDIA' | 'SALES' | 'MIXED';

// ── ساخت و ویرایش ─────────────────────────────────────────────────────
export interface ProjectInput {
  title_fa: string;
  summary: string;
  description: string;
  kind: ProjectKind;
  expected_output: string;
  difficulty: number;
  work_style: WorkStyle;
  team_size_min: number;
  team_size_max: number;
  time_commitment_hpw: number | null;
  tags: string[];
  rewards: Record<string, unknown>;
  starts_on: string | null;
  deadline_on: string | null;
  applications_close_at: string | null;
  required_skills: {
    skill_id: string;
    min_level: number;
    weight: number;
    is_teachable: boolean;
  }[];
  required_assets: { asset_id: string; is_mandatory: boolean }[];
  interests: string[];
  roles: { title_fa: string; description: string | null; slots: number }[];
  /** فقط هنگام ساخت — الگوی هشت‌مرحله‌ای شهر هوشمند برای نوع C (ADR-0016). */
  workflow?: 'CITY' | null;
}

export function createProject(input: ProjectInput, accessToken: string) {
  return apiFetch<ProjectDetail>('/projects', { method: 'POST', accessToken, body: input });
}

export function updateProject(id: string, input: ProjectInput, accessToken: string) {
  return apiFetch<ProjectDetail>(`/projects/${id}`, {
    method: 'PATCH',
    accessToken,
    body: input,
  });
}

export function fetchMyProjects(accessToken: string) {
  return apiFetch<ProjectSummary[]>('/projects/mine', { accessToken });
}

/** گذارهای §7.4 — همه یک شکل دارند، پس یک تابع کافی است. */
export function transitionProject(
  id: string,
  action: 'publish' | 'start' | 'pause' | 'resume' | 'cancel' | 'complete',
  accessToken: string,
  body?: Record<string, unknown>,
) {
  return apiFetch<ProjectDetail>(`/projects/${id}/${action}`, {
    method: 'POST',
    accessToken,
    body,
  });
}

// ── درخواست پیوستن — FR-PRJ-04 ────────────────────────────────────────
export interface Application {
  id: string;
  project_id: string;
  project_title_fa: string | null;
  applicant_id: string;
  applicant_name: string | null;
  role_id: string | null;
  role_title_fa: string | null;
  motivation: string;
  /** عکس لحظهٔ ارسال، نه عدد زندهٔ امروز — §7.5. */
  match_score: number | null;
  match_breakdown: Record<string, number> | null;
  status: ApplicationStatus;
  status_fa: string;
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface Alternative {
  project: ProjectSummary;
  match_score: number;
  reasons: Reason[];
}

export interface DecisionResult {
  application: Application;
  /** §7.5 — پاسخ رد همیشه با سه جایگزین می‌آید. */
  alternatives: Alternative[];
}

export function applyToProject(
  projectId: string,
  body: { motivation: string; role_id?: string | null },
  accessToken: string,
) {
  return apiFetch<Application>(`/projects/${projectId}/applications`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export function fetchApplications(projectId: string, accessToken: string, status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiFetch<Application[]>(`/projects/${projectId}/applications${query}`, { accessToken });
}

export function fetchMyApplications(accessToken: string) {
  return apiFetch<Application[]>('/applications/mine', { accessToken });
}

export function decideApplication(
  applicationId: string,
  body: { decision: ApplicationDecision; note?: string | null },
  accessToken: string,
) {
  return apiFetch<DecisionResult>(`/applications/${applicationId}/decide`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export function withdrawApplication(applicationId: string, accessToken: string) {
  return apiFetch<void>(`/applications/${applicationId}`, { method: 'DELETE', accessToken });
}

// ── تیم — FR-TEAM-03 ──────────────────────────────────────────────────
export interface TeamMember {
  user_id: string;
  full_name: string | null;
  username: string | null;
  role_id: string | null;
  role_title_fa: string | null;
  is_lead: boolean;
  status: 'ACTIVE' | 'LEFT' | 'REMOVED';
  joined_at: string;
  left_at: string | null;
}

export interface Team {
  project_id: string;
  name: string;
  members: TeamMember[];
  active_members: number;
  open_seats: number;
}

export function fetchTeam(projectId: string, accessToken: string) {
  return apiFetch<Team>(`/projects/${projectId}/team`, { accessToken });
}

export function removeMember(
  projectId: string,
  userId: string,
  reason: string,
  accessToken: string,
) {
  return apiFetch<void>(
    `/projects/${projectId}/team/${userId}?reason=${encodeURIComponent(reason)}`,
    { method: 'DELETE', accessToken },
  );
}

export function leaveTeam(projectId: string, reason: string, accessToken: string) {
  return apiFetch<void>(`/projects/${projectId}/leave`, {
    method: 'POST',
    accessToken,
    body: { reason },
  });
}

// ── مرحله و تحویل‌دادنی — FR-PRJ-05 ───────────────────────────────────
export interface DeliverableFile {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  purpose: string;
  scan_status: string;
  uploaded_at: string | null;
}

export interface Deliverable {
  id: string;
  milestone_id: string;
  submitter_id: string;
  submitter_name: string | null;
  version: number;
  body: string | null;
  links: string[];
  status: DeliverableStatus;
  status_fa: string;
  is_late: boolean;
  score: number | null;
  feedback: string | null;
  rubric_scores: Record<string, number> | null;
  /** شاهد ساختاریافتهٔ مرحلهٔ گردش‌کار شهری. */
  evidence: Record<string, unknown> | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  submitted_at: string;
  files: DeliverableFile[];
}

export interface Milestone {
  id: string;
  project_id: string;
  title_fa: string;
  description: string | null;
  sort_order: number;
  due_on: string | null;
  points: number;
  is_required: boolean;
  output_kind: OutputKind | null;
  output_kind_fa: string | null;
  checklist: string[];
  status: MilestoneStatus;
  status_fa: string;
  approved_at: string | null;
  /** شمارهٔ مرحله در الگوی گردش‌کار شهری؛ `null` یعنی مرحلهٔ آزاد. */
  workflow_stage: number | null;
  owner_id: string | null;
  owner_name: string | null;
  my_deliverable: Deliverable | null;
  deliverable_count: number;
}

export interface MilestoneInput {
  title_fa: string;
  description?: string | null;
  sort_order?: number;
  due_on?: string | null;
  points?: number;
  is_required?: boolean;
  output_kind?: OutputKind | null;
  checklist?: string[];
}

export function fetchMilestones(projectId: string, accessToken: string) {
  return apiFetch<Milestone[]>(`/projects/${projectId}/milestones`, { accessToken });
}

export function createMilestone(
  projectId: string,
  input: MilestoneInput,
  accessToken: string,
) {
  return apiFetch<Milestone>(`/projects/${projectId}/milestones`, {
    method: 'POST',
    accessToken,
    body: input,
  });
}

export function updateMilestone(id: string, input: MilestoneInput, accessToken: string) {
  return apiFetch<Milestone>(`/milestones/${id}`, {
    method: 'PATCH',
    accessToken,
    body: input,
  });
}

export function deleteMilestone(id: string, accessToken: string) {
  return apiFetch<void>(`/milestones/${id}`, { method: 'DELETE', accessToken });
}

export function fetchDeliverables(milestoneId: string, accessToken: string) {
  return apiFetch<Deliverable[]>(`/milestones/${milestoneId}/deliverables`, { accessToken });
}

export function submitDeliverable(
  milestoneId: string,
  body: {
    body?: string | null;
    file_ids?: string[];
    links?: string[];
    evidence?: Record<string, unknown> | null;
    checklist_confirmed?: number[];
  },
  accessToken: string,
) {
  return apiFetch<Deliverable>(`/milestones/${milestoneId}/deliverables`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export interface ReviewResult {
  deliverable: Deliverable;
  milestone: Milestone;
  /** §7.6 — همهٔ مراحل الزامی تأیید شد؟ پس پیشنهاد بستن پروژه. */
  project_ready_to_close: boolean;
  /** گردش‌کار شهری با همین تأیید کامل شد (ADR-0016). */
  workflow_completed?: boolean;
}

/** FR-CITY-01 — مسئول مرحله؛ `null` برای مرحلهٔ آزاد یعنی بی‌مسئول. */
export function assignMilestoneOwner(
  milestoneId: string,
  ownerId: string | null,
  accessToken: string,
) {
  return apiFetch<Milestone>(`/milestones/${milestoneId}/owner`, {
    method: 'PUT',
    accessToken,
    body: { owner_id: ownerId },
  });
}

export function reviewDeliverable(
  deliverableId: string,
  body: {
    decision: ReviewDecision;
    feedback?: string | null;
    score?: number | null;
    rubric_scores?: Record<string, number> | null;
  },
  accessToken: string,
) {
  return apiFetch<ReviewResult>(`/deliverables/${deliverableId}/review`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export function fetchReviewQueue(projectId: string, accessToken: string) {
  return apiFetch<Deliverable[]>(`/projects/${projectId}/review-queue`, { accessToken });
}

// ── تختهٔ وظایف — FR-PRJ-06 ───────────────────────────────────────────
export interface Task {
  id: string;
  project_id: string;
  milestone_id: string | null;
  title: string;
  description: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  status: TaskStatus;
  status_fa: string;
  due_on: string | null;
  sort_order: number;
  created_at: string;
}

export interface TaskInput {
  title: string;
  description?: string | null;
  assignee_id?: string | null;
  milestone_id?: string | null;
  due_on?: string | null;
  status?: TaskStatus;
  sort_order?: number;
}

export function fetchTasks(projectId: string, accessToken: string) {
  return apiFetch<Task[]>(`/projects/${projectId}/tasks`, { accessToken });
}

export function createTask(projectId: string, input: TaskInput, accessToken: string) {
  return apiFetch<Task>(`/projects/${projectId}/tasks`, {
    method: 'POST',
    accessToken,
    body: input,
  });
}

export function updateTask(
  projectId: string,
  taskId: string,
  input: TaskInput,
  accessToken: string,
) {
  return apiFetch<Task>(`/projects/${projectId}/tasks/${taskId}`, {
    method: 'PATCH',
    accessToken,
    body: input,
  });
}

export function deleteTask(projectId: string, taskId: string, accessToken: string) {
  return apiFetch<void>(`/projects/${projectId}/tasks/${taskId}`, {
    method: 'DELETE',
    accessToken,
  });
}

// ── گفتگو و فعالیت — FR-PRJ-06 ────────────────────────────────────────
export interface Message {
  id: string;
  parent_id: string | null;
  author_id: string;
  author_name: string | null;
  body: string;
  file_id: string | null;
  created_at: string;
  edited_at: string | null;
}

export function fetchMessages(projectId: string, accessToken: string) {
  return apiFetch<Message[]>(`/projects/${projectId}/discussion`, { accessToken });
}

export function postMessage(
  projectId: string,
  body: { body: string; parent_id?: string | null; file_id?: string | null },
  accessToken: string,
) {
  return apiFetch<Message>(`/projects/${projectId}/discussion`, {
    method: 'POST',
    accessToken,
    body,
  });
}

export function deleteMessage(projectId: string, messageId: string, accessToken: string) {
  return apiFetch<void>(`/projects/${projectId}/discussion/${messageId}`, {
    method: 'DELETE',
    accessToken,
  });
}

export interface Activity {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  kind: string;
  summary: string;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
}

export function fetchActivity(projectId: string, accessToken: string) {
  return apiFetch<Activity[]>(`/projects/${projectId}/activity`, { accessToken });
}
