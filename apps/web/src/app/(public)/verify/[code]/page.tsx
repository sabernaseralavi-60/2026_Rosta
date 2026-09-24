import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { type CertificateVerification, serverGet } from '@/lib/api/public';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/verify/[code]` — راستی‌آزمایی گواهی (§3.2، FR-PRJ-08)، SSR.
 *
 * سه حالت، هر سه صریح: معتبر (سبز)، باطل‌شده با دلیل (قرمز)، و کدی که
 * هرگز صادر نشده. گواهی باطل «یافت نشد» نمی‌گوید — کسی که پیوند را از
 * رزومه‌ای باز کرده باید بداند گواهی بوده و باطل شده (ADR-0017).
 *
 * `/verify` بی‌کد، صفحهٔ کد ورود یک‌بارمصرف است (§3.3)؛ این مسیر زیرش
 * می‌نشیند و با آن تداخل ندارد.
 */

const REVALIDATE = 60;

async function load(code: string) {
  return serverGet<CertificateVerification>(
    `/public/certificates/${encodeURIComponent(code)}`,
    REVALIDATE,
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}): Promise<Metadata> {
  const { code } = await params;
  const result = await load(code);
  if (!result.ok) return { title: 'گواهی پیدا نشد', robots: { index: false } };
  return {
    title: `گواهی ${result.data.public_code}`,
    description: `${result.data.title_fa} — ${result.data.holder_name}`,
    robots: { index: false },
  };
}

export default async function VerifyCertificatePage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const result = await load(code);

  if (!result.ok) {
    // کدی که هرگز صادر نشده ⇒ ۴۰۴ واقعی (not-found.tsx همین پوشه).
    if (result.status === 404 || result.status === 422) notFound();
    return (
      <div className="page">
        <div className="mx-auto flex max-w-[640px] flex-col gap-4 py-16 text-center">
          <h1>راستی‌آزمایی الان ممکن نیست</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            ارتباط با سامانه برقرار نشد. چند دقیقهٔ دیگر دوباره تلاش کن.
          </p>
        </div>
      </div>
    );
  }

  const cert = result.data;
  const details = cert.details;
  const rows: [string, string][] = [
    ['دارنده', cert.holder_name],
    ['نوع', cert.kind_fa],
    ['تاریخ صدور', formatDateLong(cert.issued_at)],
    ['صادرکننده', cert.issuer],
  ];
  if (details.project_kind_fa) rows.push(['نوع پروژه', details.project_kind_fa]);
  if (details.role) rows.push(['نقش', details.role === 'LEAD' ? 'مدیر پروژه' : 'عضو تیم']);
  if (details.team_size) rows.push(['اندازهٔ تیم', `${toPersianDigits(details.team_size)} نفر`]);
  if (details.course_title) rows.push(['درس', details.course_title]);
  if (details.term_title) rows.push(['نیم‌سال', details.term_title]);
  if (details.topic_title) rows.push(['موضوع پژوهش', details.topic_title]);

  return (
    <div className="page">
      <div className="mx-auto flex max-w-[720px] flex-col gap-6 py-12">
        <div
          role="status"
          className={
            cert.valid
              ? 'rounded-[var(--radius-lg)] border-2 border-[var(--success-600)] bg-[color-mix(in_oklch,var(--success-500)_10%,transparent)] px-5 py-4'
              : 'rounded-[var(--radius-lg)] border-2 border-[var(--danger-600)] bg-[color-mix(in_oklch,var(--danger-500)_10%,transparent)] px-5 py-4'
          }
        >
          <p className="text-[18px] font-bold">
            {cert.valid ? '✓ این گواهی معتبر است' : '✕ این گواهی باطل شده است'}
          </p>
          <p className="text-[14px] text-[var(--fg-secondary)]">
            {cert.valid
              ? 'سامانهٔ نوآوری و یادگیری صابر صدور این گواهی را تأیید می‌کند.'
              : `ابطال در ${cert.revoked_at ? formatDateLong(cert.revoked_at) : '—'}${cert.revoke_reason ? ` — ${cert.revoke_reason}` : ''}`}
          </p>
        </div>

        <article className="flex flex-col gap-5 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 md:p-8">
          <header className="flex flex-col gap-1">
            <p className="text-[13px] text-[var(--fg-tertiary)]">
              گواهی شمارهٔ{' '}
              <span className="font-mono" dir="ltr">
                {cert.public_code}
              </span>
            </p>
            <h1 className="text-[24px]">{cert.title_fa}</h1>
          </header>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-[15px]">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-[var(--fg-tertiary)]">{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          {cert.holder_username && (
            <Link
              href={`/u/${cert.holder_username}`}
              className="text-[14px] font-medium text-[var(--fg-brand)]"
            >
              نیمرخ عمومی {cert.holder_name} ←
            </Link>
          )}
        </article>
        <p className="text-center text-[12.5px] text-[var(--fg-tertiary)]">
          این صفحه مستقیم از پایگاه دادهٔ سامانه ساخته می‌شود؛ نسخهٔ چاپی یا تصویر گواهی را همیشه با
          همین پیوند بسنج.
        </p>
      </div>
    </div>
  );
}
