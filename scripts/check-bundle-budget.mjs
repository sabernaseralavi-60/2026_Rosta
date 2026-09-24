#!/usr/bin/env node
/**
 * دروازهٔ بودجهٔ باندل — PRD §10.11، §12.6، M7-15.
 *
 * «عبور از بودجهٔ باندل ⇒ شکست Build.»
 *
 * چرا اسکریپت خودمان و نه `@next/bundle-analyzer`: آنالایزر یک گزارش
 * تصویری می‌دهد که کسی در CI نگاهش نمی‌کند. چیزی که لازم است یک عدد
 * و یک خروج غیرصفر است.
 *
 * **«JS اولیه» یعنی آنچه مرورگر برای باز کردن یک مسیر واقعاً دانلود
 * می‌کند:** چانک‌های مشترک (`rootMainFiles`) به‌علاوهٔ چانک‌های صفحه و
 * همهٔ layoutهای بالای آن، از `app-build-manifest.json`. بودجه روی
 * **سنگین‌ترین مسیر** اعمال می‌شود.
 *
 * نسخهٔ پیش از M7-15 نام فایل‌ها را با الگوی
 * `framework|main|webpack|polyfills` می‌شمرد — چانک‌های مسیریاب pages که
 * App Router بارشان نمی‌کند، و polyfills که فقط مرورگر قدیمی می‌گیرد — و
 * دو چانک مشترک واقعی (نامشان عدد و هش است) را نمی‌دید. عددش ثابت می‌ماند
 * حتی اگر کتابخانهٔ نمودار وارد layout می‌شد.
 *
 * اندازه‌ها gzip‌شده سنجیده می‌شوند، چون کاربر ایرانی روی 4G همان را
 * دانلود می‌کند.
 *
 *   node scripts/check-bundle-budget.mjs [--json <مسیر خروجی>]
 */

import { gzipSync } from 'node:zlib';
import { readFile, readdir, stat, writeFile } from 'node:fs/promises';
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

if (!existsSync(join(BUILD_DIR, 'app-build-manifest.json'))) {
  console.error('manifest ساخت پیدا نشد. اول `pnpm --filter web build` را اجرا کنید.');
  process.exit(1);
}

const sizes = new Map();
async function gzipped(relative) {
  if (!sizes.has(relative)) {
    const bytes = await readFile(join(BUILD_DIR, relative));
    sizes.set(relative, gzipSync(bytes, { level: 9 }).length);
  }
  return sizes.get(relative);
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

/** نشانی مسیر از کلید manifest: `/(app)/projects/[id]/page` ← `/projects/[id]`. */
function routeOf(key) {
  const path = key
    .replace(/\/page$/, '')
    .split('/')
    .filter((segment) => segment && !/^\(.*\)$/.test(segment))
    .join('/');
  return `/${path}`;
}

async function measure() {
  const build = JSON.parse(await readFile(join(BUILD_DIR, 'build-manifest.json'), 'utf-8'));
  const app = JSON.parse(await readFile(join(BUILD_DIR, 'app-build-manifest.json'), 'utf-8'));
  const layouts = Object.keys(app.pages).filter((key) => key.endsWith('/layout'));

  let shared = 0;
  for (const file of build.rootMainFiles) shared += await gzipped(file);

  const routes = [];
  for (const key of Object.keys(app.pages)) {
    if (!key.endsWith('/page')) continue;
    const files = new Set([...build.rootMainFiles, ...app.pages[key]]);
    // هر layout که بخشی از مسیر صفحه است، چانک‌هایش را هم می‌فرستد.
    for (const layout of layouts) {
      const scope = layout.slice(0, -'layout'.length);
      if (key.startsWith(scope)) for (const file of app.pages[layout]) files.add(file);
    }
    let js = 0;
    let css = 0;
    for (const file of files) {
      if (file.endsWith('.js')) js += await gzipped(file);
      else if (file.endsWith('.css')) css += await gzipped(file);
    }
    routes.push({ route: routeOf(key), js, css });
  }
  routes.sort((a, b) => b.js - a.js);

  let font = 0;
  for (const file of await walk(join(WEB_ROOT, 'public'))) {
    // قلم از قبل فشرده است؛ gzip دوباره اندازه را واقعی‌تر نمی‌کند.
    if (file.endsWith('.woff2') || file.endsWith('.woff')) {
      font = Math.max(font, (await stat(file)).size);
    }
  }

  return {
    shared,
    routes,
    js: routes[0]?.js ?? 0,
    css: Math.max(0, ...routes.map((r) => r.css)),
    font,
  };
}

function format(bytes) {
  return `${(bytes / KB).toFixed(1)}KB`;
}

const measured = await measure();
let failed = false;

console.log('\nبودجهٔ باندل — PRD §10.11\n');
console.log(`  چانک‌های مشترک همهٔ مسیرها: ${format(measured.shared)}`);
console.log(`  سنگین‌ترین مسیرها (JS اولیه):`);
for (const route of measured.routes.slice(0, 5)) {
  console.log(`    ${format(route.js).padStart(9)}  ${route.route}`);
}
console.log('');

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

const jsonAt = process.argv.indexOf('--json');
if (jsonAt !== -1 && process.argv[jsonAt + 1]) {
  await writeFile(process.argv[jsonAt + 1], JSON.stringify(measured, null, 2));
}

if (failed) {
  console.error('بودجهٔ باندل رد شد. §10.11 راهبردهای کاهش را فهرست کرده است.');
  process.exit(1);
}
