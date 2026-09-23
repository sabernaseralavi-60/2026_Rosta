'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Certificate, fetchMyCertificates, verifyUrl } from '@/lib/api/public';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';

/**
 * `/me/certificates` — گواهی‌ها با پیوند اشتراک (§3.4).
 *
 * گواهی باطل‌شده پنهان نمی‌شود: دارنده باید بداند چرا پیوندش در رزومه
 * دیگر «معتبر» نشان نمی‌دهد.
 */
export function MyCertificatesView() {
  const { accessToken } = useSession();
  const [items, setItems] = useState<Certificate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchMyCertificates(accessToken)
      .then(setItems)
      .catch((cause) =>
        setError(
          cause instanceof ApiError || cause instanceof NetworkError
            ? cause.message
            : 'گواهی‌ها بارگذاری نشد.',
        ),
      );
  }, [accessToken]);

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(verifyUrl(code));
      setCopied(code);
    } catch {
      setCopied(null);
    }
  }

  if (error) {
    return (
      <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
        {error}
      </p>
    );
  }
  if (!items) return <SkeletonCard label="در حال بارگذاری گواهی‌ها" />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>گواهی‌های من</h1>
        <p className="max-w-[65ch] text-[14px] text-[var(--fg-secondary)]">
          هر گواهی یک کد و صفحهٔ راستی‌آزمایی عمومی دارد. پیوندش را در رزومه یا لینکدین بگذار؛ هر
          کسی بی‌ورود می‌تواند اصالتش را ببیند.
        </p>
      </header>
      {items.length === 0 ? (
        <EmptyState
          title="هنوز گواهی‌ای نداری"
          description="با بستن یک پروژه، تأیید یک سطح از مسیر پژوهش یا گذراندن درس، گواهی خودکار صادر می‌شود."
          action={
            <Button asChild>
              <Link href="/projects">پروژه‌ای پیدا کن</Link>
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((certificate) => (
            <li key={certificate.id}>
              <Card className="flex h-full flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={certificate.revoked_at ? 'danger' : 'success'}>
                    {certificate.revoked_at ? 'باطل‌شده' : 'معتبر'}
                  </Badge>
                  <Badge tone="neutral">{certificate.kind_fa}</Badge>
                </div>
                <CardTitle className="text-[16px]">{certificate.title_fa}</CardTitle>
                <CardDescription>
                  صادرکننده: {certificate.issuer_name} · {formatDateLong(certificate.issued_at)}
                </CardDescription>
                {certificate.revoke_reason && (
                  <p className="text-[13px] text-[var(--danger-600)]">
                    دلیل ابطال: {certificate.revoke_reason}
                  </p>
                )}
                <p className="font-mono text-[15px] tracking-wider" dir="ltr">
                  {certificate.public_code}
                </p>
                <div className="mt-auto flex flex-wrap gap-2">
                  <Button asChild variant="secondary" size="sm">
                    <Link href={certificate.verify_path}>صفحهٔ راستی‌آزمایی</Link>
                  </Button>
                  {!certificate.revoked_at && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void copy(certificate.public_code)}
                    >
                      {copied === certificate.public_code ? 'پیوند کپی شد ✓' : 'کپی پیوند'}
                    </Button>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
