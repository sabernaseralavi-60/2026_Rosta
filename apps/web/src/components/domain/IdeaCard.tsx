import Link from 'next/link';

import { VoteButton } from '@/components/domain/VoteButton';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import type { IdeaSummary } from '@/lib/api/ideas';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/** کارت ایده در بانک ایده — رأی کنار عنوان، مثل هر بانک ایدهٔ آشنا. */
export function IdeaCard({
  idea,
  accessToken,
  onError,
}: {
  idea: IdeaSummary;
  accessToken: string | null;
  onError?: (message: string) => void;
}) {
  const voteBlocked = idea.is_mine
    ? 'به ایدهٔ خودت نمی‌توانی رأی بدهی.'
    : idea.status !== 'OPEN'
      ? 'رأی‌گیری این ایده بسته است.'
      : null;

  return (
    <Card className="flex gap-4">
      <VoteButton
        ideaId={idea.id}
        count={idea.vote_count}
        voted={idea.voted_by_me}
        accessToken={accessToken}
        disabledReason={voteBlocked}
        onError={onError}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {idea.category_fa && <Badge tone="brand">{idea.category_fa}</Badge>}
          {idea.status === 'PROMOTED' && (
            <Badge tone="success">
              {idea.promoted_to_type === 'VENTURE' ? 'کسب‌وکار شد' : 'پروژه شد'}
            </Badge>
          )}
          {idea.status === 'ARCHIVED' && <Badge tone="neutral">بایگانی‌شده</Badge>}
          {idea.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} tone="neutral">
              {tag}
            </Badge>
          ))}
        </div>
        <Link
          href={`/ideas/${idea.id}`}
          className="text-[16.5px] font-semibold leading-[1.7] text-[var(--fg-primary)] hover:text-[var(--fg-brand)]"
        >
          {idea.title}
        </Link>
        <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">{idea.excerpt}</p>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          {idea.author?.name ?? (idea.is_anonymous ? 'ناشناس' : 'کاربر سیلپ')} ·{' '}
          {formatRelative(idea.created_at)} · {toPersianDigits(idea.comment_count)} نظر
        </p>
      </div>
    </Card>
  );
}
