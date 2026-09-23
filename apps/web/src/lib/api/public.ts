/**
 * دادهٔ عمومی — صفحهٔ اصلی، نیمرخ عمومی و گواهی. §5.3.1، M7-10، M7-11، ADR-0017.
 *
 * صفحه‌های عمومی سمت سرور رندر می‌شوند و مسیر نسبی `/api/v1` آنجا معنا
 * ندارد؛ `serverGet` مستقیم به `INTERNAL_API_URL` می‌رود و شکست را
 * `null` برمی‌گرداند — صفحهٔ اصلی بی‌آمار هم باید بالا بیاید.
 */

import { apiFetch } from './client';

export interface PublicStats {
  students: number;
  active_projects: number;
  completed_projects: number;
  completed_milestones: number;
  research_outputs: number;
  verified_revenue_rial: number;
  active_courses: number;
  certificates: number;
}

export interface Story {
  project_id: string;
  title_fa: string;
  summary: string;
  kind: string;
  kind_fa: string;
  course_title: string | null;
  completed_at: string | null;
  team_size: number;
  approved_milestones: number;
  members: { name: string; username: string; is_lead: boolean }[];
}

export type CertificateKind = 'PROJECT' | 'COURSE' | 'RESEARCH_LEVEL';

export interface CertificateDetails {
  project_title?: string;
  project_kind_fa?: string;
  role?: 'LEAD' | 'MEMBER';
  team_size?: number;
  course_title?: string | null;
  term_title?: string;
  level?: number;
  level_title?: string;
  topic_title?: string | null;
}

export interface Certificate {
  id: string;
  public_code: string;
  kind: CertificateKind;
  kind_fa: string;
  title_fa: string;
  issued_at: string;
  issuer_name: string;
  verify_path: string;
  details: CertificateDetails;
  revoked_at: string | null;
  revoke_reason: string | null;
}

export interface CertificateVerification {
  valid: boolean;
  public_code: string;
  kind: CertificateKind;
  kind_fa: string;
  title_fa: string;
  holder_name: string;
  holder_username: string | null;
  issued_at: string;
  issuer: string;
  details: CertificateDetails;
  revoked_at: string | null;
  revoke_reason: string | null;
}

export type ProfileSection =
  'university' | 'skills' | 'projects' | 'certificates' | 'research' | 'badges' | 'points';

export const PROFILE_SECTIONS: { key: ProfileSection; label: string }[] = [
  { key: 'university', label: 'دانشگاه، رشته و مقطع' },
  { key: 'skills', label: 'مهارت‌های برتر' },
  { key: 'projects', label: 'پروژه‌های تکمیل‌شده' },
  { key: 'certificates', label: 'گواهی‌ها' },
  { key: 'research', label: 'مسیر پژوهش و مقاله‌های راستی‌آزمایی‌شده' },
  { key: 'badges', label: 'نشان‌ها' },
  { key: 'points', label: 'امتیاز کل و سطح' },
];

export interface PublicProfile {
  username: string;
  name: string;
  bio: string | null;
  is_owner: boolean;
  is_public: boolean;
  sections: Record<ProfileSection, boolean>;
  university: string | null;
  field_of_study: string | null;
  degree_level_fa: string | null;
  skills: { title_fa: string; level: number; verified: boolean }[];
  projects: {
    id: string;
    title_fa: string;
    kind: string;
    kind_fa: string;
    role_fa: string;
    completed_at: string | null;
  }[];
  certificates: {
    public_code: string;
    kind: CertificateKind;
    title_fa: string;
    issued_at: string;
  }[];
  research_level: number | null;
  research_level_fa: string | null;
  research_outputs: {
    title: string;
    kind_fa: string;
    venue: string | null;
    doi: string | null;
    url: string | null;
  }[];
  badges: {
    code: string;
    title_fa: string;
    description: string;
    icon: string;
    tier: string;
    awarded_at: string;
  }[];
  points: { total: number; level: number; title_fa: string } | null;
  member_since: string;
}

// ── سمت سرور ─────────────────────────────────────────────────────────
export function serverApiBase(): string {
  return process.env.INTERNAL_API_URL ?? 'http://localhost:8000/api/v1';
}

export type ServerResult<T> = { ok: true; data: T } | { ok: false; status: number };

/** درخواست سمت سرور با کش ISR. شبکهٔ قطع ⇒ `status: 0`. */
export async function serverGet<T>(path: string, revalidate: number): Promise<ServerResult<T>> {
  try {
    const response = await fetch(`${serverApiBase()}${path}`, {
      headers: { Accept: 'application/json' },
      next: { revalidate },
    });
    if (!response.ok) return { ok: false, status: response.status };
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, status: 0 };
  }
}

// ── سمت کلاینت ───────────────────────────────────────────────────────
export function fetchMyCertificates(token: string) {
  return apiFetch<Certificate[]>('/me/certificates', { accessToken: token });
}

export function fetchPublicProfile(username: string, token?: string | null) {
  return apiFetch<PublicProfile>(`/profiles/${encodeURIComponent(username)}`, {
    accessToken: token ?? undefined,
  });
}

/** نشانی کامل صفحهٔ راستی‌آزمایی — برای کپی در رزومه. */
export function verifyUrl(code: string): string {
  const origin = typeof window === 'undefined' ? '' : window.location.origin;
  return `${origin}/verify/${code}`;
}
