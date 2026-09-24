import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GUIDES, readGuide, resolveGuideLink } from '@/lib/help/docs';
import { headingId, parse, render as renderMarkdown } from '@/lib/markdown/render';

/** راهنمای کاربری — M7-19. */

describe('مبدل Markdown', () => {
  it('فهرست تودرتو، جدول و نقل‌قول را می‌شناسد', () => {
    const blocks = parse('- یک\n  * زیر\n- دو\n\n| الف | ب |\n|---|---|\n| ۱ | ۲ |\n\n> نکته');
    expect(blocks.map((b) => b.kind)).toEqual(['list', 'table', 'quote']);
    const list = blocks[0];
    expect(list?.kind === 'list' && list.items[0]?.children).toHaveLength(1);
  });

  it('پیوند درون‌خطی و پررنگ را بی HTML خام می‌سازد', () => {
    render(<div>{renderMarkdown('متن **پررنگ** و [دانشجو](student.md)', resolveGuideLink)}</div>);
    expect(screen.getByText('پررنگ').tagName).toBe('STRONG');
    expect(screen.getByRole('link', { name: 'دانشجو' })).toHaveAttribute('href', '/help/student');
  });

  it('پیوند به سند فنی منتشرنشده متن ساده می‌ماند', () => {
    expect(resolveGuideLink('../ops/runbook.md')).toBeNull();
    expect(resolveGuideLink('instructor.md#درس-و-آزمون')).toBe('/help/instructor#درس-و-آزمون');
  });

  it('شناسهٔ عنوان مثل GitHub', () => {
    expect(headingId('درس و آزمون')).toBe('درس-و-آزمون');
  });
});

describe('راهنماهای docs/user', () => {
  it.each(GUIDES.map((g) => [g.slug, g.file]))('%s یک h1 دارد و پیوند شکسته ندارد', (_, file) => {
    const markdown = readGuide(file);
    const { container } = render(<article>{renderMarkdown(markdown, resolveGuideLink)}</article>);
    expect(container.querySelectorAll('h1')).toHaveLength(1);
    // هر پیوند #… به عنوانی در همان سند اشاره کند.
    const ids = new Set(Array.from(container.querySelectorAll('[id]')).map((el) => el.id));
    for (const a of Array.from(container.querySelectorAll('a[href^="#"]'))) {
      expect(ids.has(decodeURIComponent(a.getAttribute('href')!.slice(1)))).toBe(true);
    }
  });
});
