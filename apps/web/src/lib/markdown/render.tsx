import Link from 'next/link';
import type { ReactNode } from 'react';

/**
 * Markdown → React برای راهنمای کاربری — M7-19.
 *
 * چرا کتابخانه نه: راهنما در `docs/user/*.md` است و فقط زیرمجموعهٔ کوچکی از
 * Markdown را به کار می‌برد (عنوان، بند، فهرست تودرتوی یک‌سطحی، جدول، نقل‌قول،
 * کد، پررنگ، پیوند). این مبدل همان را می‌فهمد، سمت سرور و در زمان ساخت اجرا
 * می‌شود و هیچ JS به مرورگر نمی‌فرستد. HTML خام را نمی‌پذیرد: خروجی فقط
 * عنصر React است، پس `dangerouslySetInnerHTML` لازم نیست.
 */

export type LinkResolver = (href: string) => string | null;

/** شناسهٔ عنوان مثل GitHub تا پیوندهای `#…` درون سند کار کنند. */
export function headingId(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[`*]/g, '')
    .replace(/\s+/g, '-')
    .replace(/[^\p{L}\p{N}\p{M}\u200c-]/gu, '');
}

// ── درون‌خطی ─────────────────────────────────────────────────────────────

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

function inline(text: string, resolve: LinkResolver, keyPrefix: string): ReactNode[] {
  const parts = text.split(INLINE).filter((part) => part !== '');
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{inline(part.slice(2, -2), resolve, key)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={key}
          dir="ltr"
          className="rounded bg-[var(--bg-sunken)] px-1 font-mono text-[0.9em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const [, label = '', href = ''] = link;
      const target = resolve(href);
      if (target === null) return <span key={key}>{inline(label, resolve, key)}</span>;
      const className = 'font-medium text-[var(--fg-brand)] underline underline-offset-2';
      if (target.startsWith('/') || target.startsWith('#')) {
        return (
          // مسیرها از خود اسناد می‌آیند، نه از typedRoutes.
          <Link key={key} href={target as never} className={className}>
            {inline(label, resolve, key)}
          </Link>
        );
      }
      return (
        <a key={key} href={target} className={className} rel="noopener noreferrer">
          {inline(label, resolve, key)}
        </a>
      );
    }
    return part;
  });
}

// ── بلوک‌ها ───────────────────────────────────────────────────────────────

interface ListItem {
  text: string;
  children: ListItem[];
}

type Block =
  | { kind: 'heading'; level: 1 | 2 | 3; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: ListItem[] }
  | { kind: 'quote'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'table'; header: string[]; rows: string[][] }
  | { kind: 'rule' };

const LIST_ITEM = /^(\s*)(?:[-*]|\d+\.)\s+(.*)$/;

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim());
}

export function parse(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? '';

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        kind: 'heading',
        level: (heading[1]?.length ?? 1) as 1 | 2 | 3,
        text: heading[2] ?? '',
      });
      i += 1;
      continue;
    }

    if (/^---+\s*$/.test(line)) {
      blocks.push({ kind: 'rule' });
      i += 1;
      continue;
    }

    if (line.startsWith('```')) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i] ?? '').startsWith('```')) {
        body.push(lines[i] ?? '');
        i += 1;
      }
      blocks.push({ kind: 'code', text: body.join('\n') });
      i += 1;
      continue;
    }

    if (line.startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && (lines[i] ?? '').startsWith('|')) {
        rows.push(lines[i] ?? '');
        i += 1;
      }
      const [header = '', , ...body] = rows;
      blocks.push({ kind: 'table', header: cells(header), rows: body.map(cells) });
      continue;
    }

    if (line.startsWith('>')) {
      const body: string[] = [];
      while (i < lines.length && (lines[i] ?? '').startsWith('>')) {
        body.push((lines[i] ?? '').replace(/^>\s?/, ''));
        i += 1;
      }
      blocks.push({ kind: 'quote', text: body.join(' ') });
      continue;
    }

    const first = LIST_ITEM.exec(line);
    if (first) {
      const ordered = /^\s*\d+\./.test(line);
      const items: ListItem[] = [];
      while (i < lines.length) {
        const current = lines[i] ?? '';
        const match = LIST_ITEM.exec(current);
        if (match) {
          const nested = (match[1] ?? '').length >= 2;
          const item: ListItem = { text: match[2] ?? '', children: [] };
          const parent = items[items.length - 1];
          if (nested && parent) parent.children.push(item);
          else items.push(item);
          i += 1;
        } else if (current.trim() && /^\s+/.test(current)) {
          // ادامهٔ یک مورد فهرست در سطر بعد (تورفته)
          const last = items[items.length - 1];
          const target = last?.children[last.children.length - 1] ?? last;
          if (target) target.text += ` ${current.trim()}`;
          i += 1;
        } else {
          break;
        }
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }

    const body: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? '').trim() &&
      !/^(#{1,3}\s|\||>|```|---+\s*$)/.test(lines[i] ?? '') &&
      !LIST_ITEM.exec(lines[i] ?? '')
    ) {
      body.push((lines[i] ?? '').trim());
      i += 1;
    }
    blocks.push({ kind: 'paragraph', text: body.join(' ') });
  }

  return blocks;
}

function renderList(items: ListItem[], ordered: boolean, resolve: LinkResolver, key: string) {
  const Tag = ordered ? 'ol' : 'ul';
  return (
    <Tag
      key={key}
      className={`flex flex-col gap-1.5 ps-6 ${ordered ? '[list-style-type:persian]' : 'list-disc'}`}
    >
      {items.map((item, index) => (
        <li key={`${key}-${index}`} className="leading-[1.9]">
          {inline(item.text, resolve, `${key}-${index}`)}
          {item.children.length > 0 &&
            renderList(item.children, false, resolve, `${key}-${index}-c`)}
        </li>
      ))}
    </Tag>
  );
}

/**
 * بلوک‌ها به React. `# عنوان` اول سند `h1` صفحه است؛ `##` و `###` شناسه
 * می‌گیرند تا پیوندهای `#…` و فهرست صفحه کار کنند.
 */
export function render(markdown: string, resolve: LinkResolver): ReactNode[] {
  return parse(markdown).map((block, index) => {
    const key = `b${index}`;
    switch (block.kind) {
      case 'heading': {
        const content = inline(block.text, resolve, key);
        if (block.level === 1) return <h1 key={key}>{content}</h1>;
        const id = headingId(block.text);
        return block.level === 2 ? (
          <h2 key={key} id={id} className="mt-6 scroll-mt-20 text-[21px] font-semibold">
            {content}
          </h2>
        ) : (
          <h3 key={key} id={id} className="mt-3 scroll-mt-20 text-[17px] font-semibold">
            {content}
          </h3>
        );
      }
      case 'paragraph':
        return (
          <p key={key} className="leading-[2]">
            {inline(block.text, resolve, key)}
          </p>
        );
      case 'list':
        return renderList(block.items, block.ordered, resolve, key);
      case 'quote':
        return (
          <aside
            key={key}
            className="rounded-[var(--radius-md)] border-s-4 border-[var(--brand-600)] bg-[var(--bg-sunken)] p-4 leading-[1.9]"
          >
            {inline(block.text, resolve, key)}
          </aside>
        );
      case 'code':
        return (
          <pre
            key={key}
            dir="ltr"
            className="overflow-x-auto rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-4 text-[13px]"
          >
            <code>{block.text}</code>
          </pre>
        );
      case 'table':
        return (
          <div key={key} className="overflow-x-auto">
            <table className="w-full border-collapse text-[14px]">
              <thead>
                <tr>
                  {block.header.map((cell, c) => (
                    <th
                      key={c}
                      scope="col"
                      className="border-b border-[var(--border-default)] px-3 py-2 text-start font-semibold"
                    >
                      {inline(cell, resolve, `${key}-h${c}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) => (
                      <td
                        key={c}
                        className="border-b border-[var(--border-subtle)] px-3 py-2 align-top leading-[1.8]"
                      >
                        {inline(cell, resolve, `${key}-${r}-${c}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      case 'rule':
        return <hr key={key} className="border-[var(--border-subtle)]" />;
    }
  });
}
