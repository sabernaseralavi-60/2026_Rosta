#!/usr/bin/env node
/**
 * دروازهٔ بودجهٔ باندل — PRD §10.11، §12.6.
 *
 * «عبور از بودجهٔ باندل ⇒ شکست Build.»
 *
 * چرا اسکریپت خودمان و نه `@next/bundle-analyzer`: آنالایزر یک گزارش
 * تصویری می‌دهد که کسی در CI نگاهش نمی‌کند. چیزی که لازم است یک عدد
 * و یک خروج غیرصفر است.
 *
 * اندازه‌ها gzip‌شده سنجیده می‌شوند، چون کاربر ایرانی روی 4G همان را
 * دانلود می‌کند.
 */

import { gzipSync } from 'node:zlib';
import { readFile, readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const KB = 1024;

/** سقف‌های §10.11 — «سقف»، نه «هدف». عبور از سقف یعنی شکست. */
const BUDGETS = {
  js: { limit: 180 * KB, target: 140 * KB, label: 'JS اولیه' },
  css: { limit: 40 * KB, target: 25 * KB, label: 'CSS' },
  font: { limit: 120 * KB, target: 80 * KB, label: 'قلم' },
};

const WEB_ROOT = resolve(process.cwd(), 'apps/web');
const BUILD_DIR = join(WEB_ROOT, '.next');

if (!existsSync(BUILD_DIR)) {
  console.error('پوشهٔ .next پیدا نشد. اول `pnpm --filter web build` را اجرا کنید.');
  process.exit(1);
}

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => []);
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(full)));
    else files.push(full);
  }
  return files;
}

async function gzippedSize(path) {
  const bytes = await readFile(path);
  // قلم از قبل فشرده است؛ gzip دوباره اندازه را واقعی‌تر نمی‌کند.
  if (path.endsWith('.woff2')) return bytes.length;
  return gzipSync(bytes, { level: 9 }).length;
}

/**
 * «JS اولیه» یعنی آنچه هر صفحه‌ای بارگذاری می‌کند: چانک‌های مشترک.
 * چانک‌های مخصوص یک مسیر جداگانه می‌آیند و در این عدد نیستند.
 */
async function measure() {
  const staticFiles = await walk(join(BUILD_DIR, 'static'));
  const publicFiles = await walk(join(WEB_ROOT, 'public'));

  let js = 0;
  let css = 0;
  let font = 0;

  for (const file of staticFiles) {
    const size = await gzippedSize(file);
    // فقط چانک‌های مشترک: framework، main، webpack، و polyfills.
    if (file.endsWith('.js') && /[\\/]chunks[\\/]/.test(file)) {
      const isShared = /(framework|main-app|main|webpack|polyfills)[-.]/.test(file);
      if (isShared) js += size;
    } else if (file.endsWith('.css')) {
      css += size;
    }
  }

  for (const file of publicFiles) {
    if (file.endsWith('.woff2') || file.endsWith('.woff')) {
      font = Math.max(font, await stat(file).then((s) => s.size));
    }
  }

  return { js, css, font };
}

function format(bytes) {
  return `${(bytes / KB).toFixed(1)}KB`;
}

const measured = await measure();
let failed = false;

console.log('\nبودجهٔ باندل — PRD §10.11\n');

for (const [key, budget] of Object.entries(BUDGETS)) {
  const actual = measured[key];
  const over = actual > budget.limit;
  const warn = !over && actual > budget.target;

  const mark = over ? 'شکست' : warn ? 'هشدار' : 'قبول';
  console.log(
    `  ${mark.padEnd(6)} ${budget.label.padEnd(10)} ` +
      `${format(actual).padStart(9)} / سقف ${format(budget.limit)}`,
  );

  if (over) {
    failed = true;
    console.log(`         ↳ ${format(actual - budget.limit)} بیش از سقف.`);
  }
  if (warn) {
    console.log(`         ↳ از هدف (${format(budget.target)}) عبور کرده، ولی زیر سقف است.`);
  }
}

console.log('');

if (failed) {
  console.error('بودجهٔ باندل رد شد. §10.11 راهبردهای کاهش را فهرست کرده است.');
  process.exit(1);
}
