'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type ProjectLibrary, fetchProjectLibrary, projectFileUrl } from '@/lib/api/city';
import { formatBytes } from '@/lib/api/files';
import { useSession } from '@/lib/auth/use-session';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/projects/[id]/files` — کتابخانهٔ فایل پروژه، FR-PRJ-06.
 *
 * تا پیش از این، هر کس فقط فایل خودش را دانلود می‌کرد و بازبین پیوست
 * دانشجو را نمی‌دید. اینجا هر پیوست تحویل و پیام برای اعضا و سرپرستان
 * پروژه قابل دانلود است، و در پروژهٔ شهری نسخه‌های `.osm`، `.net.xml` و
 * `.rou.xml` جدا فهرست می‌شوند (FR-CITY-01).
 */
export function LibraryView({ id }: { id: string }) {
  const { accessToken, loading } = useSession();
  const [library, setLibrary] = useState<ProjectLibrary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    fetchProjectLibrary(id, accessToken)
      .then(setLibrary)
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, id, loading]);

  async function open(fileId: string) {
    if (!accessToken) return;
    try {
      const { download_url } = await projectFileUrl(id, fileId, accessToken);
      window.open(download_url, '_blank', 'noopener');
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link
          href={`/projects/${id}/workspace`}
          className="text-[13px] text-[var(--fg-tertiary)] hover:underline"
        >
          ← فضای کاری پروژه
        </Link>
        <h1>کتابخانهٔ فایل</h1>
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
      {!library && !error && <SkeletonCard label="در حال بارگذاری کتابخانه" />}

      {library && library.artifacts.length > 0 && (
        <section className="flex flex-col gap-3" aria-labelledby="artifacts-title">
          <h2 id="artifacts-title" className="text-[18px] font-semibold">
            فایل‌های مدل
          </h2>
          <div className="grid gap-4 md:grid-cols-3">
            {library.artifacts.map((artifact) => (
              <Card key={artifact.artifact} className="flex flex-col gap-2">
                <CardTitle className="text-[16px]">
                  {artifact.title_fa} <span dir="ltr">({artifact.extension})</span>
                </CardTitle>
                {artifact.versions.length === 0 ? (
                  <CardDescription>هنوز نسخه‌ای ثبت نشده است.</CardDescription>
                ) : (
                  <ul className="flex flex-col gap-2 text-[13px]">
                    {artifact.versions.map((version) => (
                      <li key={version.id} className="flex flex-col gap-0.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => void open(version.file.id)}
                            className="font-medium text-[var(--brand-700)] underline"
                          >
                            نسخهٔ {toPersianDigits(version.version)}
                          </button>
                          {version.is_current && <Badge tone="success">جاری</Badge>}
                          <Badge tone="neutral">{version.deliverable_status_fa}</Badge>
                        </div>
                        <span className="text-[12px] text-[var(--fg-tertiary)]">
                          {version.created_by_name ?? 'عضو تیم'} ·{' '}
                          {formatRelative(version.created_at)} ·{' '}
                          {formatBytes(version.file.size_bytes)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
        </section>
      )}

      {library && (
        <section className="flex flex-col gap-3" aria-labelledby="files-title">
          <h2 id="files-title" className="text-[18px] font-semibold">
            همهٔ فایل‌ها
          </h2>
          {library.files.length === 0 ? (
            <EmptyState
              title="هنوز فایلی پیوست نشده"
              description="پیوست تحویل‌ها و پیام‌های تیم اینجا جمع می‌شوند."
            />
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-md)] border border-[var(--border-subtle)]">
              {library.files.map((entry) => (
                <li
                  key={`${entry.source}-${entry.file.id}-${entry.deliverable_id ?? ''}`}
                  className="flex flex-wrap items-center justify-between gap-2 p-3 text-[13.5px]"
                >
                  <div className="flex flex-col gap-0.5">
                    <button
                      type="button"
                      onClick={() => void open(entry.file.id)}
                      className="text-start font-medium text-[var(--brand-700)] underline"
                      dir="ltr"
                    >
                      {entry.file.original_name}
                    </button>
                    <span className="text-[12px] text-[var(--fg-tertiary)]">
                      {entry.source === 'MESSAGE'
                        ? 'پیوست گفتگو'
                        : `${entry.milestone_title_fa} — نسخهٔ ${toPersianDigits(entry.deliverable_version ?? 1)}`}
                      {' · '}
                      {entry.attached_by_name ?? 'عضو تیم'}
                      {entry.attached_at && ` · ${formatRelative(entry.attached_at)}`}
                    </span>
                  </div>
                  <span className="text-[12px] text-[var(--fg-tertiary)]">
                    {formatBytes(entry.file.size_bytes)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 403) {
    return 'کتابخانهٔ فایل برای تیم پروژه است.';
  }
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کتابخانه بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
