'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import {
  ChangeSummary,
  errorText,
  ErrorLine,
  Field,
  SELECT_CLASS,
} from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import {
  type AdminUserDetail,
  fetchRoleOptions,
  fetchUser,
  grantRole,
  impersonate,
  revokeRole,
  ROLE_LABELS,
  type RoleGrant,
  type RoleOption,
  setUserStatus,
  USER_STATUS_LABELS,
  type UserStatus,
} from '@/lib/api/admin';
import { readSession, startImpersonation } from '@/lib/auth/session';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort, formatDateTime, formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin/users/[id]` — نقش، وضعیت، «مشاهده به‌عنوان» و تاریخچه (FR-ADM-01).
 *
 * هر دکمه‌ای که کنشگر اجازه‌اش را ندارد پنهان نمی‌شود بلکه پاسخ ۴۰۳ سرور
 * با پیام فارسی زیرش می‌نشیند — نقش در نشست تا ورود بعدی کهنه است و سرور
 * داور نهایی است.
 */
export function UserDetailView({ id }: { id: string }) {
  const { accessToken, session } = useSession();
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = session?.user.roles.includes('ADMIN') ?? false;

  const load = useCallback(() => {
    if (!accessToken) return;
    fetchUser(accessToken, id)
      .then(setUser)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, id]);

  useEffect(load, [load]);

  if (error && !user) return <ErrorLine>{error}</ErrorLine>;
  if (!user || !accessToken) return <SkeletonCard label="در حال بارگذاری کاربر" />;

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="مسیر" className="text-[13px] text-[var(--fg-tertiary)]">
        <Link href="/admin/users" className="hover:text-[var(--fg-brand)]">
          کاربران
        </Link>{' '}
        ‹ {user.name ?? 'کاربر'}
      </nav>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>{user.name ?? 'بی‌نام (نیمرخ ناقص)'}</h1>
          <p className="flex flex-wrap items-center gap-2 text-[13.5px] text-[var(--fg-secondary)]">
            <Badge tone={user.status === 'ACTIVE' ? 'success' : 'danger'}>
              {USER_STATUS_LABELS[user.status]}
            </Badge>
            {user.username && <span dir="ltr">@{user.username}</span>}
            <span dir="ltr">{user.mobile ?? ''}</span>
            <span dir="ltr">{user.email ?? ''}</span>
          </p>
          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            عضو از {formatDateShort(user.created_at)} ·{' '}
            {user.last_login_at
              ? `آخرین ورود ${formatRelative(user.last_login_at)}`
              : 'هنوز وارد نشده'}
          </p>
        </div>
        {user.is_public && user.username && (
          <Link
            href={`/u/${user.username}`}
            className="text-[13.5px] font-medium text-[var(--fg-brand)]"
          >
            نیمرخ عمومی ←
          </Link>
        )}
      </header>

      <dl className="grid grid-cols-2 gap-3 text-[13.5px] md:grid-cols-6">
        {[
          ['امتیاز کل', user.points_total],
          ['سطح', user.level],
          ['پروژهٔ فعال', user.projects_active],
          ['پروژهٔ تکمیل‌شده', user.projects_completed],
          ['ثبت‌نام درس', user.enrollments],
          ['گواهی معتبر', user.certificates],
        ].map(([label, value]) => (
          <div
            key={label as string}
            className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] px-3 py-2"
          >
            <dt className="text-[12px] text-[var(--fg-tertiary)]">{label}</dt>
            <dd className="text-[18px] font-semibold">{toPersianDigits(value as number)}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 xl:grid-cols-2">
        <RolesCard user={user} token={accessToken} canEdit={isAdmin} onChange={setUser} />
        <div className="flex flex-col gap-6">
          <ImpersonateCard user={user} token={accessToken} />
          {isAdmin && <StatusCard user={user} token={accessToken} onChange={setUser} />}
        </div>
      </div>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <CardTitle as="h2" className="text-[16px]">
            تاریخچهٔ حسابرسی
          </CardTitle>
          <Link
            href={`/admin/audit?user_id=${user.id}`}
            className="text-[13px] font-medium text-[var(--fg-brand)]"
          >
            همه ←
          </Link>
        </div>
        {user.recent_audit.length === 0 ? (
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            هنوز عمل حساسی دربارهٔ این کاربر ثبت نشده.
          </p>
        ) : (
          <ol className="flex flex-col gap-3">
            {user.recent_audit.map((entry) => (
              <li
                key={entry.id}
                className="flex flex-col gap-1 border-b border-[var(--border-subtle)] pb-3 last:border-0"
              >
                <span className="text-[13.5px]">
                  <strong>{entry.action_fa}</strong> — {entry.actor_name ?? 'سامانه'}
                  {entry.impersonator_name && ` (به دست ${entry.impersonator_name})`}
                </span>
                <span className="text-[12px] text-[var(--fg-tertiary)]">
                  {formatDateTime(entry.created_at)}
                </span>
                <ChangeSummary before={entry.before} after={entry.after} />
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

function RolesCard({
  user,
  token,
  canEdit,
  onChange,
}: {
  user: AdminUserDetail;
  token: string;
  canEdit: boolean;
  onChange: (user: AdminUserDetail) => void;
}) {
  const [options, setOptions] = useState<RoleOption[]>([]);
  const [role, setRole] = useState('');
  const [scope, setScope] = useState<'GLOBAL' | 'OFFERING'>('GLOBAL');
  const [scopeId, setScopeId] = useState('');
  const [expires, setExpires] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canEdit) return;
    fetchRoleOptions(token)
      .then(setOptions)
      .catch((cause) => setError(errorText(cause)));
  }, [token, canEdit]);

  const selected = options.find((option) => option.code === role);

  async function grant(event: FormEvent) {
    event.preventDefault();
    if (!role) return;
    setBusy(true);
    setError(null);
    try {
      onChange(
        await grantRole(token, user.id, {
          role,
          scope_type: scope,
          scope_id: scope === 'OFFERING' ? scopeId.trim() : undefined,
          expires_at: expires ? new Date(expires).toISOString() : undefined,
        }),
      );
      setRole('');
      setScope('GLOBAL');
      setScopeId('');
      setExpires('');
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(grant: RoleGrant) {
    const label = `${grant.title_fa}${grant.scope_label ? ` (${grant.scope_label})` : ''}`;
    if (!window.confirm(`نقش «${label}» از این کاربر گرفته شود؟`)) return;
    setError(null);
    try {
      onChange(await revokeRole(token, user.id, grant));
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <CardTitle as="h2" className="text-[16px]">
        نقش‌ها
      </CardTitle>
      <ul className="flex flex-col gap-2">
        {user.grants.map((grant) => (
          <li
            key={`${grant.code}-${grant.scope_type}-${grant.scope_id ?? ''}`}
            className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] bg-[var(--bg-sunken)] px-3 py-2"
          >
            <div className="flex flex-col text-[13.5px]">
              <span className="font-medium">
                {grant.title_fa}
                {grant.scope_label && ` — ${grant.scope_label}`}
              </span>
              <span className="text-[12px] text-[var(--fg-tertiary)]">
                {grant.granted_by_name ? `اعطا به دست ${grant.granted_by_name}، ` : ''}
                {formatDateShort(grant.granted_at)}
                {grant.expires_at && ` · انقضا ${formatDateShort(grant.expires_at)}`}
              </span>
            </div>
            {canEdit && (
              <Button variant="ghost" size="sm" onClick={() => void revoke(grant)}>
                برداشتن
              </Button>
            )}
          </li>
        ))}
      </ul>
      {user.derived_roles.length > 0 && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          نقش‌های مشتق از عضویت:{' '}
          {user.derived_roles.map((code) => ROLE_LABELS[code] ?? code).join('، ')} — از اینجا تغییر
          نمی‌کنند.
        </p>
      )}
      {canEdit && (
        <form
          onSubmit={grant}
          className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="نقش تازه">
              <select
                className={SELECT_CLASS}
                value={role}
                onChange={(event) => {
                  setRole(event.target.value);
                  setScope('GLOBAL');
                }}
              >
                <option value="">انتخاب کن…</option>
                {options.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.title_fa}
                  </option>
                ))}
              </select>
            </Field>
            {selected && selected.scopes.length > 1 && (
              <Field label="قلمرو">
                <select
                  className={SELECT_CLASS}
                  value={scope}
                  onChange={(event) => setScope(event.target.value as 'GLOBAL' | 'OFFERING')}
                >
                  <option value="GLOBAL">سراسری</option>
                  <option value="OFFERING">فقط یک ارائهٔ درس</option>
                </select>
              </Field>
            )}
          </div>
          {scope === 'OFFERING' && (
            <Input
              label="شناسهٔ ارائهٔ درس"
              hint="از نشانی صفحهٔ درس (/courses/…) بردار."
              forceLtr
              value={scopeId}
              onChange={(event) => setScopeId(event.target.value)}
            />
          )}
          <Input
            label="انقضا (اختیاری)"
            type="date"
            forceLtr
            value={expires}
            onChange={(event) => setExpires(event.target.value)}
          />
          <Button type="submit" loading={busy} disabled={!role}>
            اعطای نقش
          </Button>
        </form>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function ImpersonateCard({ user, token }: { user: AdminUserDetail; token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    const confirmText =
      `حساب «${user.name ?? 'این کاربر'}» را فقط در حالت مشاهده باز می‌کنی. ` +
      'به او اعلان داده می‌شود و هر صفحه‌ای که ببینی در لاگ حسابرسی ثبت می‌شود. ادامه؟';
    if (!window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await impersonate(token, user.id);
      if (!readSession()) throw new Error('نشست پیدا نشد.');
      startImpersonation(
        {
          accessToken: result.access_token,
          user: {
            id: result.user_id,
            display_name: result.user_name,
            username: result.username,
            roles: result.roles,
            onboarding_state: 'COMPLETE',
          },
        },
        {
          userId: result.user_id,
          userName: result.user_name,
          expiresAt: result.expires_at,
          returnTo: `/admin/users/${user.id}`,
        },
      );
      window.location.assign('/dashboard');
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle as="h2" className="text-[16px]">
        مشاهده به‌عنوان این کاربر
      </CardTitle>
      <p className="text-[13.5px] text-[var(--fg-secondary)]">
        سامانه را همان‌طور که این کاربر می‌بیند باز کن — فقط خواندنی، حداکثر ۳۰ دقیقه، با بنر قرمز
        دائمی. هیچ فرمی ارسال نمی‌شود.
      </p>
      {user.can_impersonate ? (
        <Button variant="secondary" loading={busy} onClick={() => void start()}>
          مشاهده به‌عنوان {user.name ?? 'کاربر'}
        </Button>
      ) : (
        <p className="text-[13px] text-[var(--fg-tertiary)]">
          {user.impersonation_blocked_reason ?? 'این کار برای نقش شما مجاز نیست.'}
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function StatusCard({
  user,
  token,
  onChange,
}: {
  user: AdminUserDetail;
  token: string;
  onChange: (user: AdminUserDetail) => void;
}) {
  const [status, setStatus] = useState<UserStatus>(
    user.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE',
  );
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await setUserStatus(token, user.id, status, reason.trim());
      onChange(updated);
      setReason('');
      setStatus(updated.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE');
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle as="h2" className="text-[16px]">
        وضعیت حساب
      </CardTitle>
      <p className="text-[13.5px] text-[var(--fg-secondary)]">
        تعلیق همهٔ نشست‌های باز را می‌بندد و ورود را تا فعال‌سازی دوباره متوقف می‌کند. حذف فیزیکی
        حساب از پنل ممکن نیست.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="وضعیت تازه">
          <select
            className={SELECT_CLASS}
            value={status}
            onChange={(event) => setStatus(event.target.value as UserStatus)}
          >
            {(Object.keys(USER_STATUS_LABELS) as UserStatus[])
              .filter((value) => value !== user.status)
              .map((value) => (
                <option key={value} value={value}>
                  {USER_STATUS_LABELS[value]}
                </option>
              ))}
          </select>
        </Field>
        <Textarea
          label="دلیل (در لاگ حسابرسی می‌ماند)"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={2}
        />
        <Button
          type="submit"
          variant={status === 'ACTIVE' ? 'primary' : 'danger'}
          loading={busy}
          disabled={reason.trim().length < 5}
        >
          {status === 'ACTIVE' ? 'فعال‌سازی حساب' : `تغییر به «${USER_STATUS_LABELS[status]}»`}
        </Button>
      </form>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}
