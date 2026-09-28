/**
 * محتوای عمومی (مقاله، خلاصهٔ کتاب و مقاله، مثال، Case Study) — ADR-0030.
 *
 * نوشتن محتوا اینجا نیست: مالک یادداشت‌ها را در Vault شخصی‌اش می‌نویسد و با
 * `python -m silp.scripts.vault publish --apply` منتشر می‌کند.
 */

import { apiFetch } from './client';
import { serverGet, type ServerResult } from './public';

export interface ContentCard {
  slug: string;
  kind: string;
  kind_fa: string;
  title_fa: string;
  summary: string;
  cover: string | null;
  access: string;
  access_fa: string;
  topics: string[];
  reading_minutes: number;
  published_at: string | null;
  locked: boolean;
}

export interface Facet {
  value: string;
  label: string;
  count: number;
}

export interface ContentList {
  items: ContentCard[];
  total: number;
  kinds: Facet[];
  topics: Facet[];
}

export interface ContentDetail extends ContentCard {
  skills: string[];
  course_slug: string | null;
  /** `null` وقتی `locked` است. */
  body_md: string | null;
  related: ContentCard[];
}

export interface ContentQuery {
  kind?: string;
  topic?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export const CONTENT_PAGE_SIZE = 12;

function query(params: ContentQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

/** سمت سرور، بی‌ورود: فقط آنچه عموم می‌بینند. ISR کوتاه، تا انتشار تازه زود دیده شود. */
export function fetchContentList(
  params: ContentQuery,
  revalidate = 60,
): Promise<ServerResult<ContentList>> {
  return serverGet<ContentList>(`/public/content${query(params)}`, revalidate);
}

export function fetchContentDetail(
  slug: string,
  revalidate = 60,
): Promise<ServerResult<ContentDetail>> {
  return serverGet<ContentDetail>(`/public/content/${encodeURIComponent(slug)}`, revalidate);
}

/** سمت کلاینت، با نشست کاربر: محتوای «با حساب رایگان» و «دانشجویان» را باز می‌کند. */
export function fetchContentAsViewer(slug: string, token: string) {
  return apiFetch<ContentDetail>(`/public/content/${encodeURIComponent(slug)}`, {
    accessToken: token,
  });
}
