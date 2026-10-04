/** فراخوان‌های گفت‌وگوی استاد–دانشجو — ADR-0036. */

import { apiFetch } from './client';

export type ConversationKind = 'OFFERING' | 'DIRECT' | 'GROUP';

export interface Conversation {
  id: string;
  kind: ConversationKind;
  offering_id: string;
  course_title: string;
  title: string;
  last_message_at: string | null;
  last_preview: string | null;
  unread: number;
  can_write: boolean;
}

export interface ChatMessage {
  id: string;
  sender_id: string;
  sender_name: string;
  mine: boolean;
  from_staff: boolean;
  body: string;
  reply_to_id: string | null;
  created_at: string;
  deleted: boolean;
}

export interface Thread {
  student_id: string | null;
  name: string;
  has_account: boolean;
  conversation_id: string | null;
  last_preview: string | null;
  last_message_at: string | null;
  unread: number;
}

export interface SendResult {
  sent: number;
  skipped_no_account: number;
}

export const MESSAGE_MAX = 4000;

export function fetchInbox(token: string) {
  return apiFetch<Conversation[]>('/messaging/inbox', { accessToken: token });
}

export function fetchUnread(token: string) {
  return apiFetch<{ unread: number }>('/messaging/unread', { accessToken: token });
}

export function fetchMessages(conversationId: string, token: string) {
  return apiFetch<ChatMessage[]>(`/messaging/conversations/${conversationId}/messages`, {
    accessToken: token,
  });
}

export function sendMessage(conversationId: string, body: string, token: string) {
  return apiFetch<ChatMessage>(`/messaging/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: { body },
    accessToken: token,
  });
}

export function markRead(conversationId: string, token: string) {
  return apiFetch<void>(`/messaging/conversations/${conversationId}/read`, {
    method: 'POST',
    accessToken: token,
  });
}

export function deleteMessage(messageId: string, token: string) {
  return apiFetch<void>(`/messaging/messages/${messageId}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

export function fetchThreads(offeringId: string, token: string) {
  return apiFetch<Thread[]>(`/messaging/offerings/${offeringId}/threads`, { accessToken: token });
}

export function openThread(offeringId: string, studentId: string, token: string) {
  return apiFetch<{ id: string }>(`/messaging/offerings/${offeringId}/threads/${studentId}`, {
    method: 'POST',
    accessToken: token,
  });
}

export function openChannel(offeringId: string, token: string) {
  return apiFetch<{ id: string }>(`/messaging/offerings/${offeringId}/channel`, {
    method: 'POST',
    accessToken: token,
  });
}

export function sendToAudience(
  offeringId: string,
  payload: { audience: 'ALL' | 'SELECTED'; student_ids: string[]; body: string },
  token: string,
) {
  return apiFetch<SendResult>(`/messaging/offerings/${offeringId}/send`, {
    method: 'POST',
    body: payload,
    accessToken: token,
  });
}
