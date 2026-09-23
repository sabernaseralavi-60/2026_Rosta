'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { VoteButton } from '@/components/domain/VoteButton';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type IdeaComment,
  type IdeaDetail,
  type PromotionTarget,
  addIdeaComment,
  archiveIdea,
  deleteIdea,
  deleteIdeaComment,
  fetchIdea,
  promoteIdea,
} from '@/lib/api/ideas';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong, formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/ideas/[id]` — FR-IDEA-02/03.
 *
 * نظرها نخ یک‌سطحی‌اند: پاسخ زیر نظر ریشه می‌نشیند و پاسخ به پاسخ هم زیر
 * همان ریشه. ارتقا (§7.8) فقط برای کسی که مجوزش را دارد نشان داده می‌شود
 * (`can_promote` را سرور حساب می‌کند).
 */
export function IdeaDetailView({ id }: { id: string }) {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();
  const [idea, setIdea] = useState<IdeaDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading) return;
    fetchIdea(id, accessToken)
      .then((detail) => {
        setIdea(detail);
        setError(null);
      })
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, id, sessionLoading]);

  useEffect(load, [load]);

  if (error && !idea) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="text-[15px] text-[var(--danger-600)]">
          {error}
        </p>
        <Button asChild variant="secondary" className="self-start">
          <Link href="/ideas">بازگشت به بانک ایده</Link>
        </Button>
      </div>
    );
  }
  if (!idea) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonText label="در حال بارگذاری ایده" />
        <SkeletonCard />
      </div>
    );
  }

  const roots = idea.comments.filter((c) => c.parent_id === null);
  const repliesOf = (rootId: string) => idea.comments.filter((c) => c.parent_id === rootId);

  async function remove() {
    if (!accessToken || !idea) return;
    if (!window.confirm('این ایده حذف شود؟ امتیاز ثبتش هم برمی‌گردد.')) return;
    try {
      await deleteIdea(accessToken, idea.id);
      router.push('/ideas');
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <article className="flex flex-col gap-8">
      <nav aria-label="مسیر" className="text-[13px] text-[var(--fg-tertiary)]">
        <Link href="/ideas" className="hover:text-[var(--brand-700)]">
          بانک ایده
        </Link>{' '}
        ‹ {idea.title}
      </nav>

      <header className="flex gap-4">
        <VoteButton
          ideaId={idea.id}
          count={idea.vote_count}
          voted={idea.voted_by_me}
          accessToken={accessToken}
          disabledReason={
            idea.is_mine
              ? 'به ایدهٔ خودت نمی‌توانی رأی بدهی.'
              : idea.status !== 'OPEN'
                ? 'رأی‌گیری این ایده بسته است.'
                : null
          }
          onError={setError}
        />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {idea.category_fa && <Badge tone="brand">{idea.category_fa}</Badge>}
            {idea.tags.map((tag) => (
              <Badge key={tag} tone="neutral">
                {tag}
              </Badge>
            ))}
          </div>
          <h1>{idea.title}</h1>
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {idea.author?.name ?? (idea.is_anonymous ? 'ناشناس' : 'کاربر سیلپ')} ·{' '}
            {formatDateLong(idea.created_at)}
            {idea.is_mine && idea.is_anonymous && ' · ناشناس برای دیگران'}
          </p>
        </div>
      </header>

      {idea.status === 'PROMOTED' && idea.promoted_to_id && (
        <Card variant="raised" className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[14.5px]">
            این ایده {idea.promoted_to_type === 'VENTURE' ? 'به کسب‌وکار' : 'به پروژه'} تبدیل شد
            {idea.promoted_at && ` — ${formatDateLong(idea.promoted_at)}`}.
          </p>
          <Button asChild variant="secondary" size="sm">
            <Link
              href={
                idea.promoted_to_type === 'VENTURE'
                  ? `/ventures/${idea.promoted_to_id}`
                  : `/projects/${idea.promoted_to_id}`
              }
            >
              دیدن {idea.promoted_to_type === 'VENTURE' ? 'کسب‌وکار' : 'پروژه'}
            </Link>
          </Button>
        </Card>
      )}
      {idea.status === 'ARCHIVED' && (
        <Card className="text-[14px] text-[var(--fg-secondary)]">
          این ایده بایگانی شده است{idea.archived_reason && `: ${idea.archived_reason}`}
        </Card>
      )}

      {idea.problem && (
        <section className="flex flex-col gap-2">
          <h2 className="text-[17px] font-semibold">مسئله</h2>
          <p className="whitespace-pre-line text-[15px] leading-[1.95]">{idea.problem}</p>
        </section>
      )}
      <section className="flex flex-col gap-2">
        <h2 className="text-[17px] font-semibold">شرح ایده</h2>
        <p className="whitespace-pre-line text-[15px] leading-[1.95]">{idea.body}</p>
      </section>

      {(error || notice) && (
        <p
          role={error ? 'alert' : 'status'}
          className={
            error
              ? 'text-[13.5px] text-[var(--danger-600)]'
              : 'text-[13.5px] text-[var(--success-600)]'
          }
        >
          {error ?? notice}
        </p>
      )}

      {idea.can_edit && (
        <div className="flex gap-3">
          <Button variant="danger" size="sm" onClick={remove}>
            حذف ایده
          </Button>
        </div>
      )}

      {idea.can_promote && accessToken && (
        <PromotePanel
          idea={idea}
          accessToken={accessToken}
          onDone={(href) => router.push(href)}
          onError={setError}
        />
      )}
      {idea.can_moderate && idea.status === 'OPEN' && accessToken && (
        <ArchivePanel
          ideaId={idea.id}
          accessToken={accessToken}
          onDone={() => {
            setNotice('ایده بایگانی شد.');
            load();
          }}
          onError={setError}
        />
      )}

      <section className="flex flex-col gap-4" aria-labelledby="comments-heading">
        <h2 id="comments-heading" className="text-[17px] font-semibold">
          نظرها ({toPersianDigits(idea.comment_count)})
        </h2>
        {idea.status !== 'ARCHIVED' && accessToken && (
          <CommentForm
            ideaId={idea.id}
            accessToken={accessToken}
            onPosted={load}
            onError={setError}
          />
        )}
        {roots.length === 0 ? (
          <p className="text-[14px] text-[var(--fg-tertiary)]">
            هنوز نظری ثبت نشده. اولین کسی باش که به این ایده کمک می‌کند.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {roots.map((root) => (
              <li key={root.id} className="flex flex-col gap-2">
                <CommentItem
                  comment={root}
                  accessToken={accessToken}
                  onChanged={load}
                  onError={setError}
                  replyTo={idea.status !== 'ARCHIVED' ? idea.id : null}
                />
                <ul className="flex flex-col gap-2 border-s-2 border-[var(--border-subtle)] ps-4">
                  {repliesOf(root.id).map((reply) => (
                    <li key={reply.id}>
                      <CommentItem
                        comment={reply}
                        accessToken={accessToken}
                        onChanged={load}
                        onError={setError}
                        replyTo={null}
                      />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}

function CommentForm({
  ideaId,
  accessToken,
  parentId = null,
  onPosted,
  onError,
  autoFocus = false,
}: {
  ideaId: string;
  accessToken: string;
  parentId?: string | null;
  onPosted: () => void;
  onError: (message: string) => void;
  autoFocus?: boolean;
}) {
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      await addIdeaComment(accessToken, ideaId, body.trim(), parentId);
      setBody('');
      onPosted();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <Textarea
        label={parentId ? 'پاسخ تو' : 'نظر تو'}
        rows={parentId ? 2 : 3}
        maxLength={1000}
        value={body}
        autoFocus={autoFocus}
        onChange={(event) => setBody(event.target.value)}
      />
      <Button type="submit" size="sm" loading={busy} disabled={!body.trim()} className="self-start">
        {parentId ? 'ارسال پاسخ' : 'ارسال نظر'}
      </Button>
    </form>
  );
}

function CommentItem({
  comment,
  accessToken,
  onChanged,
  onError,
  replyTo,
}: {
  comment: IdeaComment;
  accessToken: string | null;
  onChanged: () => void;
  onError: (message: string) => void;
  /** شناسهٔ ایده اگر پاسخ به این نظر مجاز است. */
  replyTo: string | null;
}) {
  const [replying, setReplying] = useState(false);

  if (comment.is_deleted) {
    return <p className="text-[13.5px] italic text-[var(--fg-tertiary)]">این نظر حذف شده است.</p>;
  }

  async function remove() {
    if (!accessToken) return;
    try {
      await deleteIdeaComment(accessToken, comment.id);
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        <span className="font-medium text-[var(--fg-secondary)]">
          {comment.author?.name ?? comment.author?.username ?? 'کاربر سیلپ'}
        </span>{' '}
        · {formatRelative(comment.created_at)}
      </p>
      <p className="whitespace-pre-line text-[14.5px] leading-[1.9]">{comment.body}</p>
      <div className="flex gap-3 text-[12.5px]">
        {replyTo && accessToken && (
          <button
            type="button"
            className="font-medium text-[var(--brand-700)] hover:underline"
            onClick={() => setReplying((value) => !value)}
          >
            {replying ? 'انصراف' : 'پاسخ'}
          </button>
        )}
        {comment.can_delete && (
          <button
            type="button"
            className="font-medium text-[var(--danger-600)] hover:underline"
            onClick={remove}
          >
            حذف
          </button>
        )}
      </div>
      {replying && replyTo && accessToken && (
        <CommentForm
          ideaId={replyTo}
          accessToken={accessToken}
          parentId={comment.id}
          autoFocus
          onPosted={() => {
            setReplying(false);
            onChanged();
          }}
          onError={onError}
        />
      )}
    </div>
  );
}

const PROJECT_KINDS = [
  { value: 'C_PROBLEM', label: 'حل مسئلهٔ واقعی' },
  { value: 'A_VENTURE', label: 'کارآفرینی' },
  { value: 'B_RESEARCH', label: 'پژوهشی' },
  { value: 'D_PERSONAL', label: 'شخصی' },
];

function PromotePanel({
  idea,
  accessToken,
  onDone,
  onError,
}: {
  idea: IdeaDetail;
  accessToken: string;
  onDone: (href: string) => void;
  onError: (message: string) => void;
}) {
  const [target, setTarget] = useState<PromotionTarget>('PROJECT');
  const [kind, setKind] = useState('C_PROBLEM');
  const [expected, setExpected] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await promoteIdea(accessToken, idea.id, {
        target,
        project_kind: kind,
        expected_output: expected.trim() || null,
      });
      onDone(result.href);
    } catch (cause) {
      onError(messageFor(cause));
      setBusy(false);
    }
  }

  return (
    <Card variant="raised">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <CardTitle>ارتقای ایده</CardTitle>
          <CardDescription>
            پروژه با مدیریت تو به‌صورت پیش‌نویس ساخته می‌شود و نویسنده به تیمش دعوت می‌شود. کسب‌وکار
            به نام خود نویسنده ثبت می‌شود.
          </CardDescription>
        </div>
        <fieldset className="flex flex-wrap gap-4 text-[14px]">
          <legend className="sr-only">مقصد ارتقا</legend>
          {(['PROJECT', 'VENTURE'] as const).map((value) => (
            <label key={value} className="flex items-center gap-2">
              <input
                type="radio"
                name="promotion-target"
                checked={target === value}
                onChange={() => setTarget(value)}
                disabled={value === 'VENTURE' && idea.is_anonymous}
                className="accent-[var(--brand-600)]"
              />
              {value === 'PROJECT' ? 'پروژه' : 'کسب‌وکار'}
              {value === 'VENTURE' && idea.is_anonymous && (
                <span className="text-[12px] text-[var(--fg-tertiary)]">(ایدهٔ ناشناس)</span>
              )}
            </label>
          ))}
        </fieldset>
        {target === 'PROJECT' && (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-[13.5px] font-medium">نوع پروژه</span>
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
              >
                {PROJECT_KINDS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <Textarea
              label="خروجی مورد انتظار"
              hint="اختیاری؛ بعداً هم قابل ویرایش است."
              rows={2}
              maxLength={500}
              value={expected}
              onChange={(event) => setExpected(event.target.value)}
            />
          </div>
        )}
        <Button type="submit" loading={busy} className="self-start">
          ارتقا به {target === 'PROJECT' ? 'پروژه' : 'کسب‌وکار'}
        </Button>
      </form>
    </Card>
  );
}

function ArchivePanel({
  ideaId,
  accessToken,
  onDone,
  onError,
}: {
  ideaId: string;
  accessToken: string;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await archiveIdea(accessToken, ideaId, reason.trim());
      onDone();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] p-4">
      <summary className="cursor-pointer text-[13.5px] font-medium text-[var(--fg-secondary)]">
        بایگانی (ناظر)
      </summary>
      <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
        <Textarea
          label="دلیل بایگانی"
          hint="به نویسنده نشان داده می‌شود."
          rows={2}
          maxLength={500}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <Button
          type="submit"
          variant="danger"
          size="sm"
          loading={busy}
          disabled={!reason.trim()}
          className="self-start"
        >
          بایگانی
        </Button>
      </form>
    </details>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
