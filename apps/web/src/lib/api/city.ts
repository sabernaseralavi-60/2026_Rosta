/**
 * آزمایشگاه شهر هوشمند و کتابخانهٔ فایل پروژه — FR-CITY-01، §7.9، ADR-0016.
 *
 * الگوی هشت‌مرحله‌ای، شاهدهای هر مرحله و چک‌لیست از **سرور** می‌آیند و
 * فرم تحویل از روی آن‌ها ساخته می‌شود — همان قاعدهٔ مسیر پژوهش. سرور
 * همهٔ کمبودها را یک‌جا در `details.missing` برمی‌گرداند.
 */

import { apiFetch } from './client';
import type { StoredFile } from './files';
import type { ProjectSummary } from './projects';
import type { DeliverableStatus, Milestone } from './workspace';

export type CityFieldKind = 'int' | 'number' | 'text' | 'url' | 'date';
export type CityStructured = 'AREA' | 'CHECKS' | 'SCENARIOS';
export type ArtifactKind = 'OSM' | 'SUMO_NET' | 'SUMO_ROUTES';

export interface CityEvidenceField {
  key: string;
  label_fa: string;
  kind: CityFieldKind;
  hint_fa: string | null;
  min_value: number | null;
  max_value: number | null;
  min_length: number | null;
  max_length: number;
}

export interface CityStageSpec {
  number: number;
  code: string;
  title_fa: string;
  deliverable_fa: string;
  points: number;
  duration_days: number;
  guide: string[];
  /** `auto`: سامانه خودش می‌سنجد؛ بقیه را تحویل‌دهنده تیک می‌زند. */
  checklist: { text: string; auto: boolean }[];
  evidence: CityEvidenceField[];
  structured: CityStructured | null;
  files: { kind: string; label_fa: string; exactly_one: boolean }[];
  min_attachments: number;
  attachments_hint_fa: string | null;
}

export interface CityOption {
  code: string;
  title_fa: string;
}

export interface CityWorkflow {
  stages: CityStageSpec[];
  total_points: number;
  total_days: number;
  area_min_km2: number;
  area_max_km2: number;
  area_max_vertices: number;
  sources: CityOption[];
  verdicts: CityOption[];
  severities: CityOption[];
  scenario_kpis: { key: string; title_fa: string }[];
  artifacts: CityOption[];
}

export interface CityArea {
  geometry: { type: string; coordinates: number[][][][] };
  area_km2: number;
  bbox: number[];
  approved: boolean;
}

export interface CityStage {
  number: number;
  milestone: Milestone;
  locked: boolean;
  open_deliverables: number;
}

export interface CityArtifactSummary {
  artifact: ArtifactKind;
  title_fa: string;
  extension: string;
  current_version: number | null;
  latest_version: number | null;
  versions: number;
}

export interface CityBoard {
  project_id: string;
  title_fa: string;
  status: string;
  lead_id: string;
  workflow_completed_at: string | null;
  current_stage: number | null;
  approved_count: number;
  area: CityArea | null;
  stages: CityStage[];
  artifacts: CityArtifactSummary[];
  can_review: boolean;
  can_manage: boolean;
}

export interface CityProject {
  project: ProjectSummary;
  current_stage: number | null;
  approved_count: number;
  area_km2: number | null;
  workflow_completed_at: string | null;
}

export interface ArtifactVersion {
  id: string;
  version: number;
  file: StoredFile;
  deliverable_id: string;
  deliverable_version: number;
  deliverable_status: DeliverableStatus;
  deliverable_status_fa: string;
  milestone_id: string;
  milestone_title_fa: string;
  created_by: string;
  created_by_name: string | null;
  created_at: string;
  is_current: boolean;
}

export interface LibraryFile {
  file: StoredFile;
  source: 'DELIVERABLE' | 'MESSAGE';
  milestone_id: string | null;
  milestone_title_fa: string | null;
  deliverable_id: string | null;
  deliverable_version: number | null;
  deliverable_status: DeliverableStatus | null;
  deliverable_status_fa: string | null;
  attached_by: string | null;
  attached_by_name: string | null;
  attached_at: string | null;
}

export interface ProjectLibrary {
  artifacts: {
    artifact: ArtifactKind;
    title_fa: string;
    extension: string;
    versions: ArtifactVersion[];
  }[];
  files: LibraryFile[];
}

export function fetchCityWorkflow() {
  return apiFetch<CityWorkflow>('/city/workflow');
}

export function fetchCityProjects() {
  return apiFetch<CityProject[]>('/city/projects');
}

export function fetchCityBoard(projectId: string, accessToken: string) {
  return apiFetch<CityBoard>(`/projects/${projectId}/city`, { accessToken });
}

export function fetchProjectLibrary(projectId: string, accessToken: string) {
  return apiFetch<ProjectLibrary>(`/projects/${projectId}/files`, { accessToken });
}

export function projectFileUrl(projectId: string, fileId: string, accessToken: string) {
  return apiFetch<{ download_url: string; expires_in: number; original_name: string }>(
    `/projects/${projectId}/files/${fileId}/download-url`,
    { accessToken },
  );
}
