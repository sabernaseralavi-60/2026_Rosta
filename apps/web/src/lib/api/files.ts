/**
 * آپلود فایل — §5.9، M2-08.
 *
 * فایل از سرور اپلیکیشن عبور نمی‌کند: کلاینت `upload-url` می‌گیرد،
 * خودش روی فضای ذخیره‌سازی `PUT` می‌کند، و بعد `complete` می‌زند تا
 * سرور حجم و Magic Number را راستی‌آزمایی کند.
 *
 * `uploadFile` هر سه گام را با هم انجام می‌دهد؛ اگر گام دوم شکست بخورد
 * هیچ‌وقت `complete` نمی‌آید و ردیف رزروشده بی‌استفاده می‌ماند — که
 * بی‌ضرر است.
 */

import { NetworkError, apiFetch } from './client';

export type FilePurpose =
  | 'DELIVERABLE'
  | 'RESOURCE'
  | 'PROJECT_COVER'
  | 'AVATAR'
  | 'MESSAGE';

export interface UploadTicket {
  file_id: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
  max_bytes: number;
}

export interface StoredFile {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  purpose: FilePurpose;
  scan_status: string;
  uploaded_at: string | null;
}

export function requestUploadUrl(
  body: {
    original_name: string;
    content_type: string;
    size_bytes: number;
    purpose: FilePurpose;
  },
  accessToken: string,
) {
  return apiFetch<UploadTicket>('/files/upload-url', {
    method: 'POST',
    accessToken,
    body,
  });
}

export function completeUpload(fileId: string, accessToken: string) {
  return apiFetch<StoredFile>(`/files/${fileId}/complete`, {
    method: 'POST',
    accessToken,
  });
}

export function fetchDownloadUrl(fileId: string, accessToken: string) {
  return apiFetch<{ download_url: string; expires_in: number; original_name: string }>(
    `/files/${fileId}/download-url`,
    { accessToken },
  );
}

/** خطای گام دوم: آپلود مستقیم روی فضای ذخیره‌سازی شکست خورد. */
export class UploadFailed extends Error {
  constructor(status: number) {
    super(
      status === 0
        ? 'آپلود فایل نیمه‌کاره ماند. اتصال اینترنت خود را بررسی کنید.'
        : 'فایل روی فضای ذخیره‌سازی نوشته نشد. دوباره تلاش کنید.',
    );
    this.name = 'UploadFailed';
  }
}

/**
 * هر سه گام §5.9، از ابتدا تا فایل آمادهٔ پیوست.
 *
 * `content_type` از خود فایل خوانده می‌شود و اگر مرورگر آن را تشخیص
 * نداده باشد خالی می‌ماند — سرور در آن حالت ردش می‌کند، که درست است:
 * نوعِ ناشناخته نباید حدس زده شود.
 */
export async function uploadFile(
  file: File,
  purpose: FilePurpose,
  accessToken: string,
): Promise<StoredFile> {
  const ticket = await requestUploadUrl(
    {
      original_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      purpose,
    },
    accessToken,
  );

  let response: Response;
  try {
    response = await fetch(ticket.upload_url, {
      method: ticket.method,
      headers: ticket.headers,
      body: file,
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }
  if (!response.ok) throw new UploadFailed(response.status);

  return completeUpload(ticket.file_id, accessToken);
}

const UNITS = ['بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت'] as const;

/** اندازهٔ فایل به فارسی — «۲٫۴ مگابایت»، نه «2400000». */
export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString('fa-IR')} ${UNITS[unit]}`;
}
