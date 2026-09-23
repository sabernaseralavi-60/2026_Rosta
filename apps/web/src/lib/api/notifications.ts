/**
 * فراخوان‌های اعلان — M6، §5.10، FR-MSG-01/02.
 *
 * ## چرا `fetch` و نه `EventSource`
 *
 * `EventSource` مرورگر هدر `Authorization` نمی‌فرستد. تنها راهش گذاشتن
 * توکن در نشانی است، و نشانی در لاگ Nginx، تاریخچهٔ مرورگر و هدر
 * `Referer` می‌ماند. پس جریان SSE با `fetch` خوانده و اینجا تجزیه می‌شود.
 */

import { apiFetch } from './client';

export type NotificationGroup = 'COURSE' | 'PROJECT' | 'SOCIAL' | 'SYSTEM';
export type NotificationPriority = 'LOW' | 'NORMAL' | 'IMPORTANT' | 'URGENT';
export type NotificationChannel = 'IN_APP' | 'EMAIL' | 'SMS' | 'TELEGRAM' | 'EITAA' | 'WHATSAPP';
export type LinkableChannel = 'TELEGRAM' | 'EITAA';

export const GROUP_LABELS: Record<NotificationGroup, string> = {
  COURSE: 'دروس',
  PROJECT: 'پروژه‌ها',
  SOCIAL: 'نشان و جامعه',
  SYSTEM: 'حساب و سامانه',
};

export const GROUPS: NotificationGroup[] = ['COURSE', 'PROJECT', 'SOCIAL', 'SYSTEM'];

export interface AppNotification {
  id: string;
  kind: string;
  group: NotificationGroup;
  group_fa: string;
  title: string;
  body: string;
  action_url: string | null;
  priority: NotificationPriority;
  created_at: string;
  read_at: string | null;
  is_read: boolean;
}

export interface NotificationFeed {
  items: AppNotification[];
  next_cursor: string | null;
}

export interface FeedFilters {
  cursor?: string | null;
  limit?: number;
  unread_only?: boolean;
  group?: NotificationGroup;
}

export interface GroupPreference {
  group: NotificationGroup;
  title_fa: string;
  description_fa: string;
  channels: NotificationChannel[];
}

export interface ChannelStatus {
  channel: NotificationChannel;
  title_fa: string;
  available: boolean;
  requires_link: boolean;
  linked: boolean;
  address_masked: string | null;
  link_flow: 'DEEP_LINK' | 'CODE' | null;
  pending_link: boolean;
}

export interface NotificationPreferences {
  groups: GroupPreference[];
  channels: ChannelStatus[];
  quiet_hours: { start: number; end: number };
}

export interface ChannelLink {
  channel: LinkableChannel;
  flow: 'DEEP_LINK' | 'CODE';
  expires_at: string;
  deep_link: string | null;
}

export function fetchNotifications(
  token: string,
  filters: FeedFilters = {},
): Promise<NotificationFeed> {
  const query = new URLSearchParams();
  if (filters.cursor) query.set('cursor', filters.cursor);
  if (filters.limit) query.set('limit', String(filters.limit));
  if (filters.unread_only) query.set('unread_only', 'true');
  if (filters.group) query.set('group', filters.group);
  const search = query.toString();
  const suffix = search ? `?${search}` : '';
  return apiFetch<NotificationFeed>(`/notifications${suffix}`, { accessToken: token });
}

export async function fetchUnreadCount(token: string): Promise<number> {
  const body = await apiFetch<{ count: number }>('/notifications/unread-count', {
    accessToken: token,
  });
  return body.count;
}

export function markNotificationRead(token: string, id: string): Promise<AppNotification> {
  return apiFetch<AppNotification>(`/notifications/${id}/read`, {
    method: 'POST',
    accessToken: token,
  });
}

export async function markAllNotificationsRead(token: string): Promise<number> {
  const body = await apiFetch<{ updated: number }>('/notifications/read-all', {
    method: 'POST',
    accessToken: token,
  });
  return body.updated;
}

export function fetchPreferences(token: string): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>('/notifications/preferences', { accessToken: token });
}

export function savePreferences(
  token: string,
  groups: Partial<Record<NotificationGroup, NotificationChannel[]>>,
): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>('/notifications/preferences', {
    method: 'PUT',
    accessToken: token,
    body: { groups },
  });
}

export function startChannelLink(
  token: string,
  channel: LinkableChannel,
  address?: string,
): Promise<ChannelLink> {
  return apiFetch<ChannelLink>(`/notifications/channels/${channel.toLowerCase()}/link`, {
    method: 'POST',
    accessToken: token,
    body: address ? { address } : {},
  });
}

export function confirmChannelLink(
  token: string,
  channel: LinkableChannel,
  code: string,
): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>(
    `/notifications/channels/${channel.toLowerCase()}/confirm`,
    { method: 'POST', accessToken: token, body: { code } },
  );
}

export function unlinkChannel(token: string, channel: LinkableChannel): Promise<void> {
  return apiFetch<void>(`/notifications/channels/${channel.toLowerCase()}`, {
    method: 'DELETE',
    accessToken: token,
  });
}

// ── SSE ───────────────────────────────────────────────────────────────
export interface SseEvent {
  event: string;
  data: string;
}

/**
 * تجزیهٔ تدریجی متن SSE. متن ناتمام (رویدادی که هنوز `\n\n` پایانی‌اش
 * نرسیده) در `rest` برمی‌گردد تا با تکهٔ بعدی دوباره تجزیه شود.
 *
 * کامنت‌ها (`: ping`) و `retry:` نادیده گرفته می‌شوند.
 */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n?/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue;
      const colon = line.indexOf(':');
      const field = colon === -1 ? line : line.slice(0, colon);
      const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '');
      if (field === 'event') event = value;
      else if (field === 'data') data.push(value);
    }
    if (data.length > 0) events.push({ event, data: data.join('\n') });
  }
  return { events, rest };
}

export interface StreamHandlers {
  onUnread: (count: number) => void;
  onNotification: (notification: AppNotification) => void;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? '/api/v1';

/**
 * یک اتصال جریان. وقتی سرور جریان را می‌بندد (هر ۱۰ دقیقه) یا شبکه قطع
 * می‌شود، promise حل یا رد می‌شود و فراخوان تصمیم می‌گیرد دوباره وصل شود.
 */
export async function readNotificationStream(
  token: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE_URL}/notifications/stream`, {
    headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token}` },
    cache: 'no-store',
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`stream ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    const parsed = parseSse(buffer + value);
    buffer = parsed.rest;
    for (const item of parsed.events) {
      dispatch(item, handlers);
    }
  }
}

function dispatch(item: SseEvent, handlers: StreamHandlers): void {
  let payload: unknown;
  try {
    payload = JSON.parse(item.data);
  } catch {
    return;
  }
  if (item.event === 'unread' && typeof payload === 'object' && payload !== null) {
    const count = (payload as { count?: unknown }).count;
    if (typeof count === 'number') handlers.onUnread(count);
  } else if (item.event === 'notification') {
    handlers.onNotification(payload as AppNotification);
  }
}
