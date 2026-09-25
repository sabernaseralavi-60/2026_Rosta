/**
 * سرویس‌کارگر سابِر — ADR-0029.
 *
 * دو کار و فقط دو کار:
 *   ۱. اعلان Push را نشان بدهد و با لمسش صفحهٔ درست را باز کند.
 *   ۲. وقتی اینترنت نیست، به‌جای صفحهٔ خطای مرورگر، `/offline.html` را نشان بدهد.
 *
 * **هیچ پاسخ API و هیچ صفحهٔ کاربر ذخیره نمی‌شود.** ذخیرهٔ صفحات پس از
 * ورود، اطلاعات یک کاربر را برای کاربر بعدیِ همان مرورگر نگه می‌داشت.
 * فقط `/offline.html` (ایستا، بی‌داده) در کش می‌ماند.
 *
 * این فایل ساخته/کامپایل نمی‌شود؛ همین‌طور که هست به مرورگر می‌رسد. پس
 * جاوااسکریپت ساده است، نه TypeScript.
 */

const CACHE = 'silp-shell-v1';
const OFFLINE_URL = '/offline.html';
const ICON = '/icons/icon-192.png';
const FALLBACK_URL = '/notifications';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add(OFFLINE_URL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

/**
 * فقط مسیر داخلی. بار Push را سرور می‌سازد، ولی سرویس‌کارگر به آن اعتماد
 * نمی‌کند: اعلانی که به سایت دیگری برود، فیشینگ است.
 */
function safePath(value) {
  if (typeof value !== 'string') return FALLBACK_URL;
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\'))
    return FALLBACK_URL;
  return value;
}

function parse(event) {
  if (!event.data) return {};
  try {
    return event.data.json();
  } catch {
    return { body: event.data.text() };
  }
}

self.addEventListener('push', (event) => {
  event.waitUntil(showPush(parse(event)));
});

async function showPush(data) {
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  // کاربر همین حالا داخل سایت است و اعلان را از جریان زنده (SSE) می‌بیند؛
  // کروم در همین حالت اجازه می‌دهد اعلان سیستمی تکراری نشان داده نشود.
  if (windows.some((client) => client.visibilityState === 'visible' && client.focused)) return;

  await self.registration.showNotification(typeof data.title === 'string' ? data.title : 'سابِر', {
    body: typeof data.body === 'string' ? data.body : '',
    icon: ICON,
    dir: 'rtl',
    lang: 'fa',
    data: { url: safePath(data.url) },
    // اعلان فوری تا لمس کاربر نمی‌رود؛ بقیه خودشان جمع می‌شوند.
    requireInteraction: data.urgent === true,
  });
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(
    safePath(event.notification.data && event.notification.data.url),
    self.location.origin,
  );
  event.waitUntil(openOrFocus(url));
});

async function openOrFocus(url) {
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of windows) {
    if (new URL(client.url).origin !== url.origin) continue;
    await client.focus();
    // `navigate` روی مشتری کنترل‌شده کار می‌کند؛ اگر نشد، پنجرهٔ تازه باز می‌شود.
    try {
      await client.navigate(url.href);
      return;
    } catch {
      break;
    }
  }
  await self.clients.openWindow(url.href);
}

// صفحه‌ای که بار نشد (نه API، نه فایل) → صفحهٔ آفلاین. بقیه بی‌دخالت می‌روند.
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.mode !== 'navigate') return;
  event.respondWith(
    fetch(request).catch(async () => (await caches.match(OFFLINE_URL)) || Response.error()),
  );
});
