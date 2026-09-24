'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { MatchRing } from '@/components/domain/MatchRing';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import type { ProjectDetail } from '@/lib/api/projects';
import {
  type Application,
  applyToProject,
  fetchMyApplications,
  withdrawApplication,
} from '@/lib/api/workspace';
import { formatDateLong } from '@/lib/format/date';

/**
 * درخواست پیوستن — FR-PRJ-04، §7.5.
 *
 * چهار شرط §7.5 را **سرور** بررسی می‌کند و پیام فارسی برمی‌گرداند؛
 * اینجا بازسازی نمی‌شوند. دلیل: نیمرخ ناقص، ظرفیت پر و سقف پنج درخواست،
 * هر سه ممکن است بین بارگذاری صفحه و کلیک کاربر عوض شوند. اعتبارسنجی
 * خوش‌بینانهٔ کلاینت فقط توهم می‌سازد.
 *
 * آنچه اینجا هست، وضعیت درخواست قبلی است: کاربری که دیروز درخواست داده
 * باید امروز ببیند کجای کار است، نه یک دکمهٔ «درخواست پیوستن» دوباره.
 */

const MAX_MOTIVATION = 500;
const MIN_MOTIVATION = 10;

export function ApplyPanel({
  project,
  accessToken,
}: {
  project: ProjectDetail;
  accessToken: string | null;
}) {
  const [existing, setExisting] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [motivation, setMotivation] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    fetchMyApplications(accessToken)
      .then((rows) => {
        if (cancelled) return;
        setExisting(rows.find((row) => row.project_id === project.id) ?? null);
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [accessToken, project.id]);

  if (!accessToken) {
    return (
      <Card className="flex flex-col gap-3">
        <CardTitle>می‌خواهی در این پروژه باشی؟</CardTitle>
        <CardDescription>
          برای ارسال درخواست باید وارد شوی. ثبت‌نام با شمارهٔ موبایل، کمتر از یک دقیقه است.
        </CardDescription>
        <Button asChild className="self-start">
          <Link href="/login">ورود یا ثبت‌نام</Link>
        </Button>
      </Card>
    );
  }

  if (loading) return null;

  if (existing && existing.status !== 'WITHDRAWN' && existing.status !== 'REJECTED') {
    return (
      <ExistingApplication
        application={existing}
        accessToken={accessToken}
        onWithdrawn={setExisting}
      />
    );
  }

  if (project.status !== 'OPEN') {
    return (
      <Card className="flex flex-col gap-2">
        <CardTitle>این پروژه فعلاً پذیرش ندارد</CardTitle>
        <CardDescription>
          وضعیت فعلی پروژه اجازهٔ عضو تازه نمی‌دهد. پروژه‌های باز را در بانک پروژه ببین.
        </CardDescription>
        <Button asChild variant="secondary" className="self-start">
          <Link href="/projects">بانک پروژه</Link>
        </Button>
      </Card>
    );
  }

  const tooShort = motivation.trim().length < MIN_MOTIVATION;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken || tooShort) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await applyToProject(
        project.id,
        { motivation: motivation.trim() },
        accessToken,
      );
      setExisting(created);
      setOpen(false);
      setMotivation('');
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-2">
        {existing?.status === 'REJECTED' && (
          <p className="text-[13px] text-[var(--fg-secondary)]">
            درخواست قبلی‌ات پذیرفته نشد
            {existing.decision_note ? `: «${existing.decision_note}»` : '.'} می‌توانی دوباره درخواست
            بدهی.
          </p>
        )}
        <Button size="lg" onClick={() => setOpen(true)}>
          درخواست پیوستن
        </Button>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          {project.open_seats > 0
            ? 'مدیر پروژه انگیزه‌نامه و نیمرخ تو را با هم می‌بیند.'
            : 'ظرفیت فعلاً پر است؛ درخواستت در فهرست انتظار می‌ماند.'}
        </p>
      </div>
    );
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <CardTitle>چرا این پروژه؟</CardTitle>
        <CardDescription>
          در چند خط بنویس چه چیزی از این پروژه می‌خواهی و چه چیزی به آن اضافه می‌کنی. این تنها چیزی
          است که مدیر پروژه کنار نیمرخت می‌خواند.
        </CardDescription>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Textarea
          label="انگیزه‌نامه"
          value={motivation}
          onChange={(event) => setMotivation(event.target.value)}
          maxLength={MAX_MOTIVATION}
          rows={5}
          placeholder="مثلاً: با SUMO کار کرده‌ام و می‌خواهم روی یک شبکهٔ واقعی تمرین کنم…"
          error={error ?? undefined}
          required
        />

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" loading={submitting} disabled={tooShort}>
            ارسال درخواست
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            انصراف
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ExistingApplication({
  application,
  accessToken,
  onWithdrawn,
}: {
  application: Application;
  accessToken: string;
  onWithdrawn: (next: Application | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleWithdraw() {
    setBusy(true);
    setError(null);
    try {
      await withdrawApplication(application.id, accessToken);
      onWithdrawn({ ...application, status: 'WITHDRAWN', status_fa: 'انصراف داده شد' });
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        {application.match_score !== null && <MatchRing score={application.match_score} />}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <CardTitle>درخواست تو</CardTitle>
            <Badge tone={application.status === 'ACCEPTED' ? 'success' : 'info'}>
              {application.status_fa}
            </Badge>
          </div>
          <CardDescription>
            ارسال‌شده در {formatDateLong(application.created_at)}
            {application.match_score !== null &&
              ' — امتیاز تطابقی که مدیر پروژه می‌بیند، همین عدد لحظهٔ ارسال است.'}
          </CardDescription>
        </div>
      </div>

      <blockquote className="border-s-2 border-[var(--border-default)] ps-3 text-[14px] leading-[1.95] text-[var(--fg-secondary)]">
        {application.motivation}
      </blockquote>

      {application.decision_note && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          پیام مدیر پروژه: «{application.decision_note}»
        </p>
      )}

      {application.status === 'ACCEPTED' ? (
        <Button asChild className="self-start">
          <Link href={`/projects/${application.project_id}/workspace`}>رفتن به فضای کاری</Link>
        </Button>
      ) : (
        <div className="flex flex-col gap-2">
          {error && (
            <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
              {error}
            </p>
          )}
          <Button
            variant="secondary"
            className="self-start"
            loading={busy}
            onClick={handleWithdraw}
          >
            انصراف از درخواست
          </Button>
        </div>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'درخواست ارسال نشد. کمی بعد دوباره تلاش کن.';
}
