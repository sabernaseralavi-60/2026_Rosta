/**
 * دریافت قلم متغیر Vazirmatn — PRD §10.3.
 *
 * قلم در مخزن نگه داشته نمی‌شود: یک فایل باینری ~۸۰KB که نسخه‌اش
 * مستقل از کد به‌روز می‌شود، در تاریخچهٔ git جایی ندارد. این اسکریپت
 * در `make setup` و در ساخت ایمیج تولید اجرا می‌شود.
 *
 * مجوز: SIL Open Font License 1.1 — https://github.com/rastikerdar/vazirmatn
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const VERSION = 'v33.003';
const SOURCE = `https://github.com/rastikerdar/vazirmatn/raw/${VERSION}/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2`;

const here = dirname(fileURLToPath(import.meta.url));
const target = resolve(here, '../public/fonts/Vazirmatn[wght].woff2');

if (existsSync(target) && !process.argv.includes('--force')) {
  console.log('قلم از قبل موجود است. برای دریافت دوباره: --force');
  process.exit(0);
}

console.log(`دریافت Vazirmatn ${VERSION}…`);

const response = await fetch(SOURCE, { redirect: 'follow' });
if (!response.ok) {
  console.error(`دریافت قلم شکست خورد: ${response.status} ${response.statusText}`);
  console.error('رابط بدون قلم هم کار می‌کند و به قلم‌های سیستمی برمی‌گردد.');
  // شکست دریافت قلم نباید ساخت را متوقف کند.
  process.exit(0);
}

const bytes = Buffer.from(await response.arrayBuffer());
await mkdir(dirname(target), { recursive: true });
await writeFile(target, bytes);

console.log(`نوشته شد: ${target} (${Math.round(bytes.length / 1024)}KB)`);
