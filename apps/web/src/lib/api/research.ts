/**
 * فراخوان‌های /research — §5.8، FR-RES-01/02/03 (M7 بخش ب، ADR-0015).
 *
 * راهنما، الگو و شاهدهای هر سطح از **سرور** می‌آیند (`steps`، `checklist`،
 * `evidence_fields`) و اینجا بازنویسی نمی‌شوند؛ متن وضعیت‌ها هم (`*_fa`).
 */

import { apiFetch } from './client';
import type { Page } from './projects';

export type LevelState = 'LOCKED' | 'AVAILABLE' | 'IN_PROGRESS' | 'SUBMITTED' | 'APPROVED';
export type SubmissionStatus = 'SUBMITTED' | 'APPROVED' | 'CHANGES_REQUESTED';
export type EvidenceKind = 'int' | 'text' | 'url' | 'date';
export type TopicStatus = 'PROPOSED' | 'OPEN' | 'RESERVED' | 'TAKEN' | 'CLOSED';
export type OutputKind = 'JOURNAL' | 'CONFERENCE' | 'THESIS' | 'REPORT' | 'PREPRINT';
export type OutputStatus =
  'DRAFT' | 'SUBMITTED' | 'UNDER_REVIEW' | 'REVISION' | 'ACCEPTED' | 'PUBLISHED' | 'REJECTED';
export type Quartile = 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'NA';
export type ReviewStatus = 'NONE' | 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface Person {
  id: string;
  name: string | null;
  username: string | null;
}

export interface FileRef {
  id: string;
  original_name: string;
}

export interface EvidenceField {
  key: string;
  label_fa: string;
  kind: EvidenceKind;
  hint_fa: string | null;
  min_value: number | null;
  min_length: number | null;
}

export interface Submission {
  id: string;
  level: number;
  version: number;
  status: SubmissionStatus;
  status_fa: string;
  summary: string;
  links: string[];
  evidence: Record<string, string | number>;
  files: FileRef[];
  topic_title: string | null;
  feedback: string | null;
  reviewer: Person | null;
  reviewed_at: string | null;
  submitted_at: string;
}

export interface Level {
  level: number;
  title_fa: string;
  deliverable_fa: string;
  points: string | null;
  state: LevelState;
  state_fa: string;
  steps: string[];
  checklist: string[];
  template_title_fa: string;
  template_columns: string[];
  evidence_fields: EvidenceField[];
  min_attachments: number;
  attachments_hint_fa: string | null;
  mentor: Person | null;
  started_at: string | null;
  approved_at: string | null;
  submissions: Submission[];
}

export interface TopicBrief {
  id: string;
  title: string;
  status: TopicStatus;
  status_fa: string;
  idle_days_left: number | null;
}

export interface Track {
  levels: Level[];
  current_level: number | null;
  topic: TopicBrief | null;
  can_participate: boolean;
  can_review: boolean;
  completed: boolean;
}

export interface SubmitInput {
  summary: string;
  links: string[];
  file_ids: string[];
  evidence: Record<string, string | number>;
}

export interface ReviewItem extends Submission {
  student: Person;
  level_title_fa: string;
  evidence_fields: EvidenceField[];
  checklist: string[];
  previous: {
    version: number;
    status: SubmissionStatus;
    feedback: string | null;
    reviewed_at: string | null;
  }[];
}

export function fetchTrack(accessToken?: string | null) {
  return apiFetch<Track>('/research/tracks', { accessToken });
}

export function submitLevel(accessToken: string, level: number, input: SubmitInput) {
  return apiFetch<Submission>(`/research/tracks/${level}/submit`, {
    method: 'POST',
    accessToken,
    body: input,
  });
}

export function fetchResearchReviewQueue(accessToken: string) {
  return apiFetch<ReviewItem[]>('/research/review-queue', { accessToken });
}

export function reviewSubmission(
  accessToken: string,
  submissionId: string,
  decision: 'APPROVED' | 'CHANGES_REQUESTED',
  feedback?: string,
) {
  return apiFetch<Submission>(`/research/submissions/${submissionId}/review`, {
    method: 'POST',
    accessToken,
    body: { decision, feedback: feedback || null },
  });
}

export function submissionFileUrl(accessToken: string, submissionId: string, fileId: string) {
  return apiFetch<{ download_url: string; expires_in: number; original_name: string }>(
    `/research/submissions/${submissionId}/files/${fileId}/download-url`,
    { accessToken },
  );
}

// ── بانک موضوع ────────────────────────────────────────────────────────
export interface Topic {
  id: string;
  title: string;
  description: string;
  prerequisites: string | null;
  level: number | null;
  status: TopicStatus;
  status_fa: string;
  proposer: Person;
  reserved_by: Person | null;
  reserved_by_me: boolean;
  reserved_at: string | null;
  idle_days_left: number | null;
  review_note: string | null;
  is_mine: boolean;
  can_edit: boolean;
  can_manage: boolean;
  can_reserve: boolean;
  can_release: boolean;
  created_at: string;
}

export interface TopicInput {
  title: string;
  description: string;
  prerequisites: string | null;
  level: number | null;
}

export function fetchTopics(
  filters: { status?: TopicStatus; level?: number; q?: string; mine?: boolean; page?: number },
  accessToken?: string | null,
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value));
  }
  const query = params.toString();
  return apiFetch<Page<Topic>>(`/research/topics${query ? `?${query}` : ''}`, { accessToken });
}

export function fetchTopic(id: string, accessToken?: string | null) {
  return apiFetch<Topic>(`/research/topics/${id}`, { accessToken });
}

export function createTopic(accessToken: string, input: TopicInput) {
  return apiFetch<Topic>('/research/topics', { method: 'POST', accessToken, body: input });
}

export function updateTopic(accessToken: string, id: string, input: TopicInput) {
  return apiFetch<Topic>(`/research/topics/${id}`, { method: 'PATCH', accessToken, body: input });
}

export type TopicAction = 'reserve' | 'release' | 'reopen';

export function topicAction(accessToken: string, id: string, action: TopicAction) {
  return apiFetch<Topic>(`/research/topics/${id}/${action}`, { method: 'POST', accessToken });
}

export function reviewTopic(
  accessToken: string,
  id: string,
  decision: 'APPROVE' | 'REJECT',
  note?: string,
) {
  return apiFetch<Topic>(`/research/topics/${id}/review`, {
    method: 'POST',
    accessToken,
    body: { decision, note: note || null },
  });
}

export function closeTopic(accessToken: string, id: string, reason: string) {
  return apiFetch<Topic>(`/research/topics/${id}/close`, {
    method: 'POST',
    accessToken,
    body: { reason },
  });
}

// ── خروجی پژوهشی ──────────────────────────────────────────────────────
export interface Output {
  id: string;
  kind: OutputKind;
  kind_fa: string;
  title: string;
  authors: string;
  venue: string | null;
  quartile: Quartile | null;
  status: OutputStatus;
  status_fa: string;
  doi: string | null;
  url: string | null;
  file: FileRef | null;
  project: { id: string; title: string } | null;
  submitted_on: string | null;
  published_on: string | null;
  verified_stage: 'SUBMITTED' | 'ACCEPTED' | 'PUBLISHED' | null;
  verified_quartile: Quartile | null;
  review_status: ReviewStatus;
  review_status_fa: string;
  review_note: string | null;
  reviewed_at: string | null;
  points: string;
  is_scored: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface OutputReviewItem extends Output {
  owner: Person;
}

export interface OutputInput {
  kind: OutputKind;
  title: string;
  authors: string;
  status: OutputStatus;
  venue: string | null;
  quartile: Quartile | null;
  doi: string | null;
  url: string | null;
  submitted_on: string | null;
  published_on: string | null;
}

export function fetchMyOutputs(accessToken: string) {
  return apiFetch<Output[]>('/research/outputs', { accessToken });
}

export function createOutput(accessToken: string, input: OutputInput) {
  return apiFetch<Output>('/research/outputs', { method: 'POST', accessToken, body: input });
}

export function updateOutput(accessToken: string, id: string, input: OutputInput) {
  return apiFetch<Output>(`/research/outputs/${id}`, {
    method: 'PATCH',
    accessToken,
    body: input,
  });
}

export function deleteOutput(accessToken: string, id: string) {
  return apiFetch<void>(`/research/outputs/${id}`, { method: 'DELETE', accessToken });
}

export function fetchOutputReviewQueue(accessToken: string) {
  return apiFetch<OutputReviewItem[]>('/research/outputs/review-queue', { accessToken });
}

export function reviewOutput(
  accessToken: string,
  id: string,
  decision: 'VERIFIED' | 'REJECTED',
  note?: string,
) {
  return apiFetch<Output>(`/research/outputs/${id}/review`, {
    method: 'POST',
    accessToken,
    body: { decision, note: note || null },
  });
}
