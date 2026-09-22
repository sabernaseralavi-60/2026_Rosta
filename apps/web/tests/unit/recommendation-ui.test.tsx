import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MatchRing } from '@/components/domain/MatchRing';
import { ReasonList } from '@/components/domain/ReasonList';
import { ChoiceCard } from '@/components/ui/ChoiceCard';
import { Progress } from '@/components/ui/Progress';
import { SkillSlider } from '@/components/ui/SkillSlider';
import type { Reason } from '@/lib/api/projects';

const LEVEL_LABELS: Record<number, string> = {
  1: 'نمی‌دانم',
  2: 'آشنایی مقدماتی دارم',
  3: 'با کمک می‌توانم کار کنم',
  4: 'مستقل کار می‌کنم',
  5: 'می‌توانم به دیگران آموزش دهم',
};

describe('MatchRing — §10.6', () => {
  it('درصد را با ارقام فارسی نشان می‌دهد', () => {
    render(<MatchRing score={86.4} />);
    expect(screen.getByRole('img').textContent).toContain('۸۶');
  });

  it('عدد فقط با رنگ منتقل نمی‌شود — §10.2', () => {
    render(<MatchRing score={42} />);
    // برچسب دسترس‌پذیر هم بازه را می‌گوید، هم عدد را.
    expect(screen.getByRole('img')).toHaveAccessibleName(/تطابق کم.*۴۲/);
  });

  it('بازه‌ها طبق سند تفکیک می‌شوند: ≥۸۰، ۶۰-۸۰، <۶۰', () => {
    const { rerender } = render(<MatchRing score={80} />);
    expect(screen.getByRole('img')).toHaveAccessibleName(/تطابق بالا/);

    rerender(<MatchRing score={65} />);
    expect(screen.getByRole('img')).toHaveAccessibleName(/تطابق متوسط/);

    rerender(<MatchRing score={30} />);
    expect(screen.getByRole('img')).toHaveAccessibleName(/تطابق کم/);
  });

  it('مقدار خارج از بازه را مهار می‌کند', () => {
    const { rerender } = render(<MatchRing score={140} />);
    expect(screen.getByRole('img').textContent).toContain('۱۰۰');

    rerender(<MatchRing score={-20} />);
    expect(screen.getByRole('img').textContent).toContain('۰');
  });
});

describe('ReasonList — §8.10', () => {
  const reasons: Reason[] = [
    {
      type: 'ASSET_MATCH',
      polarity: 'POSITIVE',
      contribution: 20,
      text: 'موتور داری و این پروژه به آن نیاز دارد',
    },
    {
      type: 'SKILL_GAP',
      polarity: 'WARNING',
      contribution: -4.5,
      text: 'طراحی گرافیک لازم است و تو در سطح ۲ هستی',
    },
  ];

  it('متن سرور را بدون تغییر نمایش می‌دهد', () => {
    render(<ReasonList reasons={reasons} />);
    for (const reason of reasons) {
      expect(screen.getByText(reason.text)).toBeInTheDocument();
    }
  });

  it('مثبت و هشدار را برای صفحه‌خوان تفکیک می‌کند — §10.2', () => {
    render(<ReasonList reasons={reasons} />);
    const items = screen.getAllByRole('listitem');
    expect(within(items[0]!).getByText('نقطهٔ قوت:')).toBeInTheDocument();
    expect(within(items[1]!).getByText('هشدار:')).toBeInTheDocument();
  });

  it('با فهرست خالی چیزی رندر نمی‌کند', () => {
    const { container } = render(<ReasonList reasons={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('SkillSlider — FR-PROF-01', () => {
  function Harness({ initial = null }: { initial?: number | null }) {
    const [value, setValue] = useState<number | null>(initial);
    return (
      <SkillSlider
        label="پایتون"
        value={value}
        onChange={setValue}
        levelLabels={LEVEL_LABELS}
      />
    );
  }

  it('«پاسخ‌نداده» را از «سطح ۱» جدا نشان می‌دهد', () => {
    render(<Harness />);
    expect(screen.getByText('هنوز پاسخ نداده‌ای')).toBeInTheDocument();
    expect(screen.queryByText(LEVEL_LABELS[1]!)).not.toBeInTheDocument();
  });

  it('پس از انتخاب، متن توصیفی همان سطح را نشان می‌دهد', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('radio', { name: /^4/ }));

    expect(screen.getByText(LEVEL_LABELS[4]!)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^4/ })).toHaveAttribute('aria-checked', 'true');
  });

  it('مقدار انتخاب‌شده را به بالا گزارش می‌دهد', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SkillSlider label="آر" value={null} onChange={onChange} levelLabels={LEVEL_LABELS} />,
    );

    await user.click(screen.getByRole('radio', { name: /^2/ }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('هر سطح، متن توصیفی‌اش را در نام دسترس‌پذیر دارد', () => {
    render(<Harness initial={3} />);
    expect(
      screen.getByRole('radio', { name: `5 — ${LEVEL_LABELS[5]}` }),
    ).toBeInTheDocument();
  });
});

describe('ChoiceCard — §10.6', () => {
  it('وضعیت انتخاب را به ورودی بومی می‌سپارد', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ChoiceCard
        name="assets"
        value="laptop"
        checked={false}
        onChange={onChange}
        label="لپ‌تاپ"
      />,
    );

    await user.click(screen.getByRole('checkbox', { name: /لپ‌تاپ/ }));
    expect(onChange).toHaveBeenCalledWith('laptop');
  });

  it('حالت رادیو نقش درست را می‌گیرد', () => {
    render(
      <ChoiceCard
        type="radio"
        name="goal"
        value="INCOME"
        checked
        onChange={() => {}}
        label="درآمد"
        hint="می‌خواهم درآمد واقعی داشته باشم"
      />,
    );

    const radio = screen.getByRole('radio', { name: /درآمد/ });
    expect(radio).toBeChecked();
    expect(screen.getByText('می‌خواهم درآمد واقعی داشته باشم')).toBeInTheDocument();
  });
});

describe('Progress — §10.6', () => {
  it('همیشه برچسب عددی دارد', () => {
    render(<Progress value={2} max={4} label="پیشرفت" />);
    expect(screen.getByText('۲ از ۴')).toBeInTheDocument();
  });

  it('مقادیر ARIA را درست می‌گذارد', () => {
    render(<Progress value={3} max={4} label="پیشرفت" />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '3');
    expect(bar).toHaveAttribute('aria-valuemax', '4');
  });

  it('مقدار بیش از سقف را مهار می‌کند', () => {
    render(<Progress value={9} max={4} label="پیشرفت" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');
  });
});
