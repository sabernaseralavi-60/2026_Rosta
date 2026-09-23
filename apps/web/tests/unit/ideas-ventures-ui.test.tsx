import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { IdeaCard } from '@/components/domain/IdeaCard';
import { StageTrack } from '@/components/domain/StageTrack';
import { VoteButton } from '@/components/domain/VoteButton';
import { ChipGroup } from '@/components/ui/ChipGroup';
import { ApiError } from '@/lib/api/client';
import * as ideas from '@/lib/api/ideas';
import type { IdeaSummary } from '@/lib/api/ideas';

afterEach(() => {
  vi.restoreAllMocks();
});

function idea(overrides: Partial<IdeaSummary> = {}): IdeaSummary {
  return {
    id: 'i-1',
    title: 'اپلیکیشن هم‌سفری دانشجویی',
    excerpt: 'دانشجویان خوابگاهی هر روز با تاکسی جداگانه به دانشگاه می‌روند.',
    category: 'TRANSPORT',
    category_fa: 'حمل‌ونقل و ترافیک',
    tags: ['حمل‌ونقل'],
    status: 'OPEN',
    is_anonymous: false,
    author: { id: 'u-1', name: 'نسترن رستمی', username: 'nastaran' },
    vote_count: 4,
    comment_count: 2,
    voted_by_me: false,
    is_mine: false,
    promoted_to_type: null,
    promoted_to_id: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('VoteButton — FR-IDEA-02', () => {
  it('رأی را خوش‌بینانه می‌شمارد و با پاسخ سرور هم‌تراز می‌کند', async () => {
    const vote = vi
      .spyOn(ideas, 'voteIdea')
      .mockResolvedValue({ idea_id: 'i-1', vote_count: 5, voted_by_me: true });
    render(<VoteButton ideaId="i-1" count={4} voted={false} accessToken="t" />);

    await userEvent.click(screen.getByRole('button'));

    expect(vote).toHaveBeenCalledWith('t', 'i-1', true);
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByRole('button')).toHaveTextContent('۵');
  });

  it('رأی تکراری از تب دیگر را حالت درست می‌گیرد، نه خطا', async () => {
    vi.spyOn(ideas, 'voteIdea').mockRejectedValue(
      new ApiError(409, {
        code: 'DUPLICATE_VOTE',
        message: 'شما قبلاً به این ایده رأی داده‌اید.',
        details: {},
        trace_id: 't',
      }),
    );
    const onError = vi.fn();
    render(<VoteButton ideaId="i-1" count={4} voted={false} accessToken="t" onError={onError} />);

    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true'));
    expect(onError).not.toHaveBeenCalled();
  });

  it('خطای دیگر رأی را برمی‌گرداند و پیام می‌دهد', async () => {
    vi.spyOn(ideas, 'voteIdea').mockRejectedValue(new Error('قطع شد'));
    const onError = vi.fn();
    render(<VoteButton ideaId="i-1" count={4} voted={false} accessToken="t" onError={onError} />);

    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('قطع شد'));
    expect(screen.getByRole('button')).toHaveTextContent('۴');
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');
  });

  it('بدون ورود یا روی ایدهٔ خود غیرفعال است و دلیلش را می‌گوید', () => {
    render(
      <VoteButton
        ideaId="i-1"
        count={0}
        voted={false}
        accessToken="t"
        disabledReason="به ایدهٔ خودت نمی‌توانی رأی بدهی."
      />,
    );
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'به ایدهٔ خودت نمی‌توانی رأی بدهی.');
  });
});

describe('IdeaCard — بانک ایده', () => {
  it('نویسندهٔ ایدهٔ ناشناس را «ناشناس» نشان می‌دهد', () => {
    render(<IdeaCard idea={idea({ is_anonymous: true, author: null })} accessToken={null} />);
    expect(screen.getByText(/ناشناس/)).toBeInTheDocument();
    expect(screen.queryByText(/نسترن/)).not.toBeInTheDocument();
  });

  it('ایدهٔ ارتقایافته نشان مقصد دارد و رأی نمی‌پذیرد', () => {
    render(
      <IdeaCard
        idea={idea({ status: 'PROMOTED', promoted_to_type: 'VENTURE', promoted_to_id: 'v-1' })}
        accessToken="t"
      />,
    );
    expect(screen.getByText('کسب‌وکار شد')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /رأی/ })).toBeDisabled();
  });
});

describe('StageTrack — §7.7', () => {
  it('مرحلهٔ جاری را با aria-current می‌گوید', () => {
    render(<StageTrack stage="MVP" />);
    const current = screen.getByText('محصول کمینه').closest('li');
    expect(current).toHaveAttribute('aria-current', 'step');
  });

  it('کسب‌وکار متوقف، مرحلهٔ پیش از توقف را نگه می‌دارد', () => {
    render(<StageTrack stage="PAUSED" pausedFrom="VALIDATION" />);
    expect(screen.getByText('اعتبارسنجی').closest('li')).toHaveAttribute('aria-current', 'step');
  });
});

describe('ChipGroup', () => {
  it('گزینهٔ انتخاب‌شده را با aria-pressed اعلام می‌کند', async () => {
    const onChange = vi.fn();
    render(
      <ChipGroup
        label="مرتب‌سازی"
        options={[
          { value: 'hot', label: 'داغ' },
          { value: 'new', label: 'تازه' },
        ]}
        value="hot"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('button', { name: 'داغ' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'تازه' }));
    expect(onChange).toHaveBeenCalledWith('new');
  });
});
