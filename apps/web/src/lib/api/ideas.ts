/** فراخوان‌های /ideas — قرارداد §5.8، FR-IDEA-01/02/03 (M7). */

import { apiFetch } from './client';
import type { Page } from './projects';

export type IdeaStatus = 'OPEN' | 'PROMOTED' | 'ARCHIVED';
export type IdeaSort = 'hot' | 'new' | 'top';
export type IdeaCategory =
  | 'TRANSPORT'
  | 'AGRICULTURE'
  | 'COMMERCE'
  | 'EDUCATION'
  | 'TECHNOLOGY'
  | 'ENVIRONMENT'
  | 'SOCIAL'
  | 'OTHER';
export type PromotionTarget = 'PROJECT' | 'VENTURE';

/** نویسنده — برای ایدهٔ ناشناس `null` است، مگر برای خود نویسنده. */
export interface IdeaAuthor {
  id: string;
  name: string | null;
  username: string | null;
}

export interface IdeaSummary {
  id: string;
  title: string;
  excerpt: string;
  category: IdeaCategory | null;
  category_fa: string | null;
  tags: string[];
  status: IdeaStatus;
  is_anonymous: boolean;
  author: IdeaAuthor | null;
  vote_count: number;
  comment_count: number;
  voted_by_me: boolean;
  is_mine: boolean;
  promoted_to_type: PromotionTarget | null;
  promoted_to_id: string | null;
  created_at: string;
}

export interface IdeaComment {
  id: string;
  parent_id: string | null;
  /** نظر حذف‌شده‌ای که پاسخ زنده دارد، متن و نویسنده ندارد. */
  body: string | null;
  author: IdeaAuthor | null;
  is_deleted: boolean;
  is_mine: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface IdeaDetail extends IdeaSummary {
  body: string;
  problem: string | null;
  archived_reason: string | null;
  promoted_at: string | null;
  comments: IdeaComment[];
  can_edit: boolean;
  can_promote: boolean;
  can_moderate: boolean;
}

export interface IdeaInput {
  title: string;
  body: string;
  problem: string | null;
  category: IdeaCategory | null;
  tags: string[];
  is_anonymous: boolean;
}

export interface IdeaCategoryOption {
  code: IdeaCategory;
  title_fa: string;
}

export interface IdeaFilters {
  q?: string;
  category?: IdeaCategory;
  tag?: string;
  status?: IdeaStatus;
  mine?: boolean;
  sort?: IdeaSort;
  page?: number;
}

export function fetchIdeaCategories() {
  return apiFetch<IdeaCategoryOption[]>('/ideas/categories');
}

export function fetchIdeas(filters: IdeaFilters, accessToken?: string | null) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value));
  }
  const query = params.toString();
  return apiFetch<Page<IdeaSummary>>(`/ideas${query ? `?${query}` : ''}`, { accessToken });
}

export function fetchIdea(id: string, accessToken?: string | null) {
  return apiFetch<IdeaDetail>(`/ideas/${id}`, { accessToken });
}

export function createIdea(accessToken: string, input: IdeaInput) {
  return apiFetch<IdeaDetail>('/ideas', { method: 'POST', accessToken, body: input });
}

export function deleteIdea(accessToken: string, id: string) {
  return apiFetch<void>(`/ideas/${id}`, { method: 'DELETE', accessToken });
}

export function archiveIdea(accessToken: string, id: string, reason: string) {
  return apiFetch<IdeaDetail>(`/ideas/${id}/archive`, {
    method: 'POST',
    accessToken,
    body: { reason },
  });
}

export interface VoteResult {
  idea_id: string;
  vote_count: number;
  voted_by_me: boolean;
}

export function voteIdea(accessToken: string, id: string, vote: boolean) {
  return apiFetch<VoteResult>(`/ideas/${id}/vote`, {
    method: vote ? 'POST' : 'DELETE',
    accessToken,
  });
}

export function addIdeaComment(
  accessToken: string,
  id: string,
  body: string,
  parentId: string | null = null,
) {
  return apiFetch<IdeaComment>(`/ideas/${id}/comments`, {
    method: 'POST',
    accessToken,
    body: { body, parent_id: parentId },
  });
}

export function deleteIdeaComment(accessToken: string, commentId: string) {
  return apiFetch<void>(`/ideas/comments/${commentId}`, { method: 'DELETE', accessToken });
}

export interface PromotionResult {
  target_type: PromotionTarget;
  target_id: string;
  href: string;
}

export function promoteIdea(
  accessToken: string,
  id: string,
  body: { target: PromotionTarget; project_kind?: string; expected_output?: string | null },
) {
  return apiFetch<PromotionResult>(`/ideas/${id}/promote`, {
    method: 'POST',
    accessToken,
    body,
  });
}
