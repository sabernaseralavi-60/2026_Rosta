/**
 * ساخت آیکون‌های PWA — ADR-0029.
 *
 *     node scripts/gen-pwa-icons.mjs
 *
 * خروجی در `public/icons/` می‌نشیند و در گیت می‌ماند: ساخت آیکون به
 * مرورگر و فونت نیاز دارد و نباید بخشی از `pnpm build` شود. فقط وقتی
 * برند عوض شد دوباره اجرا کن.
 *
 * حرف «س» با همان فونت وزیرمتن سایت رسم می‌شود (کروم شکل‌دهی فارسی را
 * درست انجام می‌دهد؛ کتابخانه‌های تصویر نه). نسخهٔ `maskable` تمام‌صفحه
 * است و حرف داخل ناحیهٔ امن ۸۰٪ می‌ماند تا اندروید هر برشی بزند، نبُرَد.
 */

import { mkdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'public', 'icons');

// رنگ برند `--brand-600` (oklch(54% 0.114 182)) — همان `theme_color` مانیفست.
const BRAND = '#008374';

const font = (await readFile(join(root, 'public', 'fonts', 'Vazirmatn[wght].woff2'))).toString(
  'base64',
);

const ICONS = [
  { file: 'icon-192.png', size: 192, glyph: 0.62, radius: 0.22 },
  { file: 'icon-512.png', size: 512, glyph: 0.62, radius: 0.22 },
  { file: 'icon-maskable-512.png', size: 512, glyph: 0.46, radius: 0 },
  { file: 'apple-touch-icon.png', size: 180, glyph: 0.62, radius: 0 },
];

function page({ size, glyph, radius }) {
  return `<!doctype html><meta charset="utf-8"><style>
    @font-face { font-family: V; src: url(data:font/woff2;base64,${font}) format('woff2'); font-weight: 100 900; }
    html, body { margin: 0; background: transparent; }
    .icon {
      width: ${size}px; height: ${size}px; box-sizing: border-box;
      background: ${BRAND}; border-radius: ${Math.round(size * radius)}px;
      display: grid; place-items: center; overflow: hidden;
    }
    .icon span {
      font: 800 ${Math.round(size * glyph)}px/1 V; color: #fff; direction: rtl;
      /* حرف «س» شکم پایین خط زمینه می‌افتد؛ بالا می‌آید تا وسط دیده شود. */
      transform: translateY(-${Math.round(size * 0.11)}px);
    }
  </style><div class="icon"><span>س</span></div>`;
}

await mkdir(out, { recursive: true });
const browser = await chromium.launch();
try {
  for (const icon of ICONS) {
    const context = await browser.newContext({
      viewport: { width: icon.size, height: icon.size },
      deviceScaleFactor: 1,
    });
    const tab = await context.newPage();
    await tab.setContent(page(icon));
    await tab.evaluate(() => document.fonts.ready);
    await tab.screenshot({
      path: join(out, icon.file),
      omitBackground: true,
      clip: { x: 0, y: 0, width: icon.size, height: icon.size },
    });
    await context.close();
    console.log(`public/icons/${icon.file}`);
  }
} finally {
  await browser.close();
}
