/**
 * فراخوان‌های /teams — §5.8، FR-TEAM-01/02/03 (M7 بخش ب، ADR-0015).
 *
 * دلیل مکملیت (`complement_reason`) و «قوی‌تر از تو» (`stronger_reason`)
 * متن فارسی آمادهٔ سرورند — §8.14 «تولید دلیل قابل‌فهم اجباری است».
 */

import { apiFetch } from './client';
import type { Page } from './projects';

export type TargetKind = 'PROJECT' | 'VENTURE';
export type EffectiveOpeningStatus = 'OPEN' | 'FILLED' | 'CLOSED' | 'EXPIRED';
export type ApplicationStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'WITHDRAWN';

export interface Person {
  id: string;
  name: string | null;
  username: string | null;
}

export interface Teammate {
  user: { id: string; username: string | null; display_name: string; university: string | null };
  bio: string | null;
  weekly_hours: number | null;
  top_skills: { skill_id: string; title_fa: string; level: number; verified: boolean }[];
  assets: string[];
  shares_course: boolean;
  complement_score: number | null;
  complement_reason: string | null;
  complement_skills: string[];
  stronger_skills: string[];
  stronger_reason: string | null;
}

export interface TeamSearch {
  items: Teammate[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  context: {
    project: { id: string; title: string } | null;
    gaps: { title_fa: string; min_level: number }[];
    can_invite: boolean;
    my_profile_is_public: boolean;
  };
}

export interface SearchFilters {
  skill_id?: string;
  min_level?: number;
  asset_id?: string;
  interest_id?: string;
  university_id?: string;
  q?: string;
  complement_project_id?: string;
  page?: number;
}

export interface ManagedTeam {
  kind: TargetKind;
  id: string;
  title: string;
  roles: { id: string; title: string }[];
}

function query(filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : '';
}

export function searchTeammates(accessToken: string, filters: SearchFilters) {
  return apiFetch<TeamSearch>(`/teams/search${query(filters)}`, { accessToken });
}

export function fetchManagedTeams(accessToken: string) {
  return apiFetch<ManagedTeam[]>('/teams/managed', { accessToken });
}

// ── آگهی ──────────────────────────────────────────────────────────────
export interface OpeningApplication {
  id: string;
  opening_id: string;
  applicant: Person;
  message: string;
  status: ApplicationStatus;
  status_fa: string;
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface Opening {
  id: string;
  title: string;
  description: string;
  needed_skills: { id: string; title_fa: string }[];
  commitment_hpw: number | null;
  role: { id: string; title: string } | null;
  status: 'OPEN' | 'FILLED' | 'CLOSED';
  effective_status: EffectiveOpeningStatus;
  status_fa: string;
  expires_at: string;
  created_at: string;
  target: { kind: TargetKind; id: string; title: string; href: string };
  poster: Person;
  pending_count: number | null;
  has_applied: boolean;
  can_manage: boolean;
}

export interface OpeningDetail extends Opening {
  my_application: OpeningApplication | null;
  applications: OpeningApplication[];
}

export interface MyApplication extends OpeningApplication {
  opening_title: string;
  target: Opening['target'];
}

export interface OpeningInput {
  project_id?: string | null;
  venture_id?: string | null;
  title: string;
  description: string;
  needed_skill_ids: string[];
  commitment_hpw: number | null;
  role_id: string | null;
}

export function fetchOpenings(
  filters: { q?: string; skill_id?: string; kind?: TargetKind; mine?: boolean; page?: number },
  accessToken?: string | null,
) {
  return apiFetch<Page<Opening>>(`/teams/openings${query(filters)}`, { accessToken });
}

export function fetchOpening(id: string, accessToken?: string | null) {
  return apiFetch<OpeningDetail>(`/teams/openings/${id}`, { accessToken });
}

export function createOpening(accessToken: string, input: OpeningInput) {
  return apiFetch<OpeningDetail>('/teams/openings', { method: 'POST', accessToken, body: input });
}

export function openingAction(accessToken: string, id: string, action: 'close' | 'renew') {
  return apiFetch<OpeningDetail>(`/teams/openings/${id}/${action}`, {
    method: 'POST',
    accessToken,
  });
}

export function applyToOpening(accessToken: string, id: string, message: string) {
  return apiFetch<OpeningApplication>(`/teams/openings/${id}/apply`, {
    method: 'POST',
    accessToken,
    body: { message },
  });
}

export function decideApplication(
  accessToken: string,
  id: string,
  decision: 'ACCEPTED' | 'DECLINED',
  note?: string,
) {
  return apiFetch<OpeningApplication>(`/teams/applications/${id}/decide`, {
    method: 'POST',
    accessToken,
    body: { decision, note: note || null },
  });
}

export function withdrawApplication(accessToken: string, id: string) {
  return apiFetch<void>(`/teams/applications/${id}/withdraw`, { method: 'POST', accessToken });
}

export function fetchMyOpeningApplications(accessToken: string) {
  return apiFetch<MyApplication[]>('/teams/applications/mine', { accessToken });
}

/** دعوت مستقیم از نتیجهٔ جستجو — همان مسیرهای دعوت M7 بخش الف. */
export function inviteToProject(accessToken: string, projectId: string, username: string) {
  return apiFetch<unknown>(`/projects/${projectId}/invitations`, {
    method: 'POST',
    accessToken,
    body: { username },
  });
}
