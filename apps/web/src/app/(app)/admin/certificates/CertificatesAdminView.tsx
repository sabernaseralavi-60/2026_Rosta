'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { revokeCertificate, searchCertificates } from '@/lib/api/admin';
import type { Certificate } from '@/lib/api/public';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';

/**
 * `/admin/certificates` — ابطال گواهی (ADR-0017).
 *
 * صدور دستی عمداً نیست: گواهی فقط از رویداد واقعی (بستن پروژه، تأیید سطح،
 * نمرهٔ قبولی) می‌آید. ابطال پاک نمی‌کند — صفحهٔ راستی‌آزمایی «باطل شد» و
 * دلیلش را نشان می‌دهد.
 */
export function CertificatesAdminView() {
  const { accessToken } = useSession();
  const [code, setCode] = useState('');
  const [query, setQuery] = useState<string | null>(null);
  const [rows, setRows] = useState<Certificate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    searchCertificates(accessToken, query ? { code: query } : {})
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, query]);

  useEffect(load, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setRows(null);
    setQuery(code.trim() || null);
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>گواهی‌ها</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          گواهی خودکار صادر می‌شود؛ اینجا فقط جستجو و ابطال با دلیل است.
        </p>
      </header>
      <form onSubmit={submit} className="flex items-end gap-3">
        <div className="flex-1">
          <Input
            label="کد گواهی"
            placeholder="مثلاً 7KQ2-MX9P"
            forceLtr
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </div>
        <Button type="submit">جستجو</Button>
      </form>
      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonRow label="در حال بارگذاری گواهی‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title={query ? 'گواهی با این کد نیست' : 'هنوز گواهی‌ای صادر نشده'}
          description="گواهی با بستن پروژه، تأیید سطح پژوهش یا نمرهٔ قبولی درس صادر می‌شود."
        />
      )}
      {rows && rows.length > 0 && (
        <ul className="flex flex-col gap-3">
          {rows.map((certificate) => (
            <CertificateRow
              key={certificate.id}
              certificate={certificate}
              token={accessToken ?? ''}
              onRevoked={(updated) =>
                setRows((current) =>
                  (current ?? []).map((c) => (c.id === updated.id ? updated : c)),
                )
              }
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function CertificateRow({
  certificate,
  token,
  onRevoked,
}: {
  certificate: Certificate;
  token: string;
  onRevoked: (certificate: Certificate) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function revoke(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onRevoked(await revokeCertificate(token, certificate.id, reason.trim()));
      setOpen(false);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-2 font-medium">
              {certificate.title_fa}
              {certificate.revoked_at ? (
                <Badge tone="danger">باطل‌شده</Badge>
              ) : (
                <Badge tone="success">معتبر</Badge>
              )}
            </span>
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {certificate.kind_fa} · صادرکننده: {certificate.issuer_name} ·{' '}
              {formatDateShort(certificate.issued_at)} ·{' '}
              <Link
                href={certificate.verify_path}
                className="font-mono text-[var(--brand-700)]"
                dir="ltr"
              >
                {certificate.public_code}
              </Link>
            </span>
            {certificate.revoke_reason && (
              <span className="text-[12.5px] text-[var(--danger-600)]">
                دلیل ابطال: {certificate.revoke_reason}
              </span>
            )}
          </div>
          {!certificate.revoked_at && !open && (
            <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
              ابطال
            </Button>
          )}
        </div>
        {open && (
          <form onSubmit={revoke} className="flex flex-col gap-2">
            <Textarea
              label="دلیل ابطال (روی صفحهٔ راستی‌آزمایی نشان داده می‌شود)"
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            {error && <ErrorLine>{error}</ErrorLine>}
            <div className="flex gap-2">
              <Button
                type="submit"
                variant="danger"
                size="sm"
                loading={busy}
                disabled={reason.trim().length < 5}
              >
                ابطال گواهی
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
                انصراف
              </Button>
            </div>
          </form>
        )}
      </Card>
    </li>
  );
}
