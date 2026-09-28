import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContentCard } from '@/components/public/ContentCard';
import type { ContentCard as Card } from '@/lib/api/content';
import { resolveContentLink } from '@/lib/markdown/links';
import { parse, render as renderMarkdown } from '@/lib/markdown/render';
import { externalCover, isPhotoKey, PHOTOS, photoKeyFor } from '@/lib/photos';

/** موتور محتوا — ADR-0030: فرمول، پیوند امن، عکس روی‌جلد و کارت مطلب. */

const CARD: Card = {
  slug: 'four-step-model',
  kind: 'ARTICLE',
  kind_fa: 'مقالهٔ آموزشی',
  title_fa: 'چرا مدل چهارمرحله‌ای هنوز زنده است؟',
  summary: 'خلاصهٔ کوتاه',
  cover: null,
  access: 'PUBLIC',
  access_fa: 'عمومی',
  topics: ['برنامه‌ریزی حمل‌ونقل'],
  reading_minutes: 3,
  published_at: '2026-09-27T06:00:00Z',
  locked: false,
};

describe('فرمول در مبدل Markdown', () => {
  it('فرمول بلوکی تک‌سطری و چندسطری را می‌شناسد', () => {
    const blocks = parse('$$x^2$$\n\nمتن\n\n$$\na + b\n= c\n$$');
    expect(blocks.map((b) => b.kind)).toEqual(['math', 'paragraph', 'math']);
    expect(blocks[0]?.kind === 'math' && blocks[0].text).toBe('x^2');
    expect(blocks[2]?.kind === 'math' && blocks[2].text).toBe('a + b\n= c');
  });

  it('فرمول بلوکی بند پیشین را قطع می‌کند', () => {
    const blocks = parse('یک بند\n$$y$$');
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'math']);
  });

  it('KaTeX فرمول را رندر می‌کند و برای صفحه‌خوان نسخهٔ MathML دارد', () => {
    const { container } = render(
      <div>{renderMarkdown('نتیجه $\\alpha + 1$ است.\n\n$$T = \\beta_0$$', () => null)}</div>,
    );
    expect(container.querySelectorAll('.katex').length).toBe(2);
    expect(container.querySelector('math')).not.toBeNull();
    // getByRole در jsdom روی MathML می‌شکند؛ با انتخابگر مستقیم می‌سنجیم.
    expect(container.querySelector('[role="math"]')).toHaveAttribute('dir', 'ltr');
  });

  it('علامت دلار در متن معمولی فرمول حساب نمی‌شود', () => {
    const { container } = render(
      <div>{renderMarkdown('قیمت $5 و $ 6 ریال نیست، ولی $x$ هست.', () => null)}</div>,
    );
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
    expect(container.textContent).toContain('$5');
  });

  it('فرمول خراب خطا نمی‌اندازد و صفحه را نمی‌شکند', () => {
    expect(() =>
      render(<div>{renderMarkdown('$$\\frac{1}{$$\n\nبعدی', () => null)}</div>),
    ).not.toThrow();
    expect(screen.getByText('بعدی')).toBeInTheDocument();
  });
});

describe('پیوندهای مطلب', () => {
  it('فقط داخلی، لنگر و https', () => {
    expect(resolveContentLink('/content/x')).toBe('/content/x');
    expect(resolveContentLink('#بخش')).toBe('#بخش');
    expect(resolveContentLink('https://example.org')).toBe('https://example.org');
  });

  it('http، javascript و مسیر بی‌پروتکل متن ساده می‌شوند', () => {
    expect(resolveContentLink('http://example.org')).toBeNull();
    expect(resolveContentLink('javascript:alert(1)')).toBeNull();
    expect(resolveContentLink('//evil.example')).toBeNull();
    expect(resolveContentLink('file.md')).toBeNull();
  });
});

describe('عکس‌های سایت', () => {
  it('کلید ثبت‌شده برنده است، وگرنه پیش‌فرض نوع', () => {
    expect(photoKeyFor('research', 'ARTICLE')).toBe('research');
    expect(photoKeyFor(null, 'BOOK_SUMMARY')).toBe('collab');
    expect(photoKeyFor('نامعلوم', 'PAPER_SUMMARY')).toBe('research');
    expect(photoKeyFor(null, 'KIND_NOBODY_KNOWS')).toBe('learn');
  });

  it('فقط نشانی https بیرونی پذیرفته می‌شود', () => {
    expect(externalCover('https://example.org/a.jpg')).toBe('https://example.org/a.jpg');
    expect(externalCover('http://example.org/a.jpg')).toBeNull();
    expect(externalCover('hero')).toBeNull();
    expect(isPhotoKey('hero')).toBe(true);
    expect(isPhotoKey('constructor')).toBe(false); // نه از prototype
  });

  it('هر عکس ثبت‌شده متن جایگزین و ابعاد دارد', () => {
    for (const photo of Object.values(PHOTOS)) {
      expect(photo.alt.length).toBeGreaterThan(10);
      expect(photo.width).toBeGreaterThan(photo.height);
      expect(photo.src).toMatch(/^\/photos\/[a-z]+\.jpg$/);
    }
  });
});

describe('کارت مطلب', () => {
  it('یک پیوند دارد و نشان دسترسی را فقط برای غیرعمومی می‌آورد', () => {
    const { rerender } = render(<ContentCard item={CARD} />);
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/content/four-step-model');
    expect(screen.queryByText('عمومی')).toBeNull();

    rerender(
      <ContentCard item={{ ...CARD, access: 'PREMIUM', access_fa: 'ویژه', locked: true }} />,
    );
    expect(screen.getByText(/ویژه/)).toBeInTheDocument();
    expect(screen.getByText(/🔒/)).toBeInTheDocument();
  });

  it('زمان مطالعه را با رقم فارسی می‌نویسد', () => {
    render(<ContentCard item={CARD} />);
    expect(screen.getByText(/۳ دقیقه مطالعه/)).toBeInTheDocument();
  });
});
