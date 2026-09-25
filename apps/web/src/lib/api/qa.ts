/**
 * فراخوان‌های پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.
 *
 * دسترسی و «چه کسی چه می‌تواند بکند» از سرور می‌آید (`can_*`، `is_manager`)؛
 * رابط آن‌ها را بازسازی نمی‌کند.
 */

import { apiFetch } from './client';
import type { Page } from './projects';

export type QaFilter = 'all' | 'unanswered' | 'unresolved' | 'mine';

export interface QaAuthor {
  id: string;
  name: string | null;
  username: string | null;
}

export interface QaReply {
  id: string;
  thread_id: string;
  body: string;
  author: QaAuthor;
  /** پاسخ را خودِ استاد نوشته. */
  is_official: boolean;
  helpful_count: number;
  voted_by_me: boolean;
  /** استاد این پاسخ را تأیید کرده. */
  is_endorsed: boolean;
  endorsed_at: string | null;
  is_mine: boolean;
  can_vote: boolean;
  can_endorse: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface QaThreadSummary {
  id: string;
  offering_id: string;
  week_number: number | null;
  title: string;
  excerpt: string;
  /** برای پرسش ناشناسِ دیگران `null`. */
  author: QaAuthor | null;
  is_anonymous: boolean;
  is_resolved: boolean;
  reply_count: number;
  has_official_answer: boolean;
  is_mine: boolean;
  created_at: string;
}

export interface QaThreadDetail extends QaThreadSummary {
  body: string;
  replies: QaReply[];
  can_resolve: boolean;
  can_delete: boolean;
  is_manager: boolean;
}

export interface QaThreadInput {
  title: string;
  body: string;
  week_number?: number | null;
  is_anonymous?: boolean;
}

export interface QaListOptions {
  filter?: QaFilter;
  weekNumber?: number | null;
  page?: number;
  pageSize?: number;
}

export function fetchQaThreads(
  offeringId: string,
  accessToken: string,
  { filter = 'all', weekNumber = null, page = 1, pageSize = 20 }: QaListOptions = {},
) {
  const params = new URLSearchParams({ filter, page: String(page), page_size: String(pageSize) });
  if (weekNumber !== null) params.set('week_number', String(weekNumber));
  return apiFetch<Page<QaThreadSummary>>(`/offerings/${offeringId}/qa/threads?${params}`, {
    accessToken,
  });
}

export function createQaThread(offeringId: string, input: QaThreadInput, accessToken: string) {
  return apiFetch<QaThreadDetail>(`/offerings/${offeringId}/qa/threads`, {
    method: 'POST',
    accessToken,
    body: input,
  });
}

export function fetchQaThread(threadId: string, accessToken: string) {
  return apiFetch<QaThreadDetail>(`/qa/threads/${threadId}`, { accessToken });
}

export function setQaResolved(threadId: string, isResolved: boolean, accessToken: string) {
  return apiFetch<QaThreadDetail>(`/qa/threads/${threadId}`, {
    method: 'PATCH',
    accessToken,
    body: { is_resolved: isResolved },
  });
}

export function deleteQaThread(threadId: string, accessToken: string) {
  return apiFetch<void>(`/qa/threads/${threadId}`, { method: 'DELETE', accessToken });
}

export function postQaReply(threadId: string, body: string, accessToken: string) {
  return apiFetch<QaReply>(`/qa/threads/${threadId}/replies`, {
    method: 'POST',
    accessToken,
    body: { body },
  });
}

export function deleteQaReply(replyId: string, accessToken: string) {
  return apiFetch<void>(`/qa/replies/${replyId}`, { method: 'DELETE', accessToken });
}

export function voteQaReply(replyId: string, on: boolean, accessToken: string) {
  return apiFetch<QaReply>(`/qa/replies/${replyId}/vote`, {
    method: on ? 'POST' : 'DELETE',
    accessToken,
  });
}

export function endorseQaReply(replyId: string, on: boolean, accessToken: string) {
  return apiFetch<QaReply>(`/qa/replies/${replyId}/endorse`, {
    method: on ? 'POST' : 'DELETE',
    accessToken,
  });
}
