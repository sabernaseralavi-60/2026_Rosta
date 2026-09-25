/**
 * اعلان Push وب — ADR-0029.
 *
 * سه چیز اینجاست: ثبت سرویس‌کارگر، روشن/خاموش‌کردن اشتراک **این مرورگر**، و
 * رها کردن اشتراک هنگام خروج. اشتراک به مرورگر گره است، نه به حساب؛ پس
 * «روشن کردن» فقط برای همین دستگاه است و دستگاه‌های دیگر دست‌نخورده می‌مانند.
 *
 * ## چرا هنگام خروج رها می‌شود
 *
 * رایانهٔ مشترک (آزمایشگاه دانشگاه): دانشجوی اول خارج می‌شود، ولی اشتراک
 * مرورگر می‌ماند و اعلان‌های او روی صفحهٔ دانشجوی بعدی پدیدار می‌شد. خروج
 * اشتراک را هم از سرور و هم از مرورگر برمی‌دارد.
 */

import { apiFetch } from '@/lib/api/client';

export const SERVICE_WORKER_URL = '/sw.js';
const SUBSCRIPTIONS = '/notifications/push/subscriptions';

export type PushSupport = 'supported' | 'unsupported' | 'needs-install';

/** خطای قابل‌نمایش به کاربر — پیام فارسی آماده. */
export class PushError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PushError';
  }
}

/**
 * آیا این مرورگر می‌تواند Push بگیرد؟
 *
 * آیفون فقط برنامهٔ **نصب‌شده** روی صفحهٔ اصلی را Push می‌دهد؛ تب سافاری
 * `PushManager` ندارد. برای این حالت راهنمای نصب نشان می‌دهیم، نه «پشتیبانی
 * نمی‌شود» — چون با یک مرحله حل می‌شود.
 */
export function pushSupport(): PushSupport {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return 'unsupported';
  if ('PushManager' in window && 'Notification' in window) return 'supported';
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const installed =
    globalThis.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !installed ? 'needs-install' : 'unsupported';
}

/** کلید عمومی VAPID (base64 امن‌برای‌URL) به بایت — قالبی که `subscribe` می‌خواهد. */
export function urlBase64ToBytes(value: string): Uint8Array {
  const padded =
    value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export interface SubscriptionBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

/** `PushSubscription.toJSON()` با اعتبارسنجی — کلیدها در مرورگرهای قدیمی ممکن است نباشند. */
export function subscriptionBody(subscription: PushSubscription): SubscriptionBody {
  const json = subscription.toJSON();
  const p256dh = json.keys?.p256dh;
  const auth = json.keys?.auth;
  if (!json.endpoint || !p256dh || !auth) {
    throw new PushError('مرورگر اطلاعات کامل اشتراک را نداد. مرورگر را به‌روز کن.');
  }
  return { endpoint: json.endpoint, keys: { p256dh, auth } };
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return null;
  try {
    return await navigator.serviceWorker.register(SERVICE_WORKER_URL, { scope: '/' });
  } catch {
    // ثبت‌نشدنِ سرویس‌کارگر نباید سایت را بشکند؛ فقط Push و آفلاین نیست.
    return null;
  }
}

/** اشتراک فعلی همین مرورگر، اگر باشد. */
export async function currentSubscription(): Promise<PushSubscription | null> {
  if (pushSupport() !== 'supported') return null;
  try {
    const registration = await navigator.serviceWorker.ready;
    return await registration.pushManager.getSubscription();
  } catch {
    return null;
  }
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  return typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
}

/** روشن‌کردن برای این مرورگر. خروجی: شمار دستگاه‌های کاربر پس از ثبت. */
export async function enablePush(token: string, publicKey: string): Promise<number> {
  if (pushSupport() !== 'supported') {
    throw new PushError('این مرورگر اعلان وب را پشتیبانی نمی‌کند.');
  }
  // مجوز را فقط پس از کلیک کاربر می‌خواهیم؛ درخواست بی‌مقدمه مسدودسازی می‌آورد.
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new PushError(
      permission === 'denied'
        ? 'مرورگر اعلان این سایت را مسدود کرده. از تنظیمات سایت در مرورگر آزادش کن.'
        : 'اجازهٔ اعلان داده نشد.',
    );
  }

  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    try {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToBytes(publicKey) as BufferSource,
      });
    } catch {
      // معمولاً سرویس Push مرورگر (مثل FCM برای کروم) در دسترس نیست.
      throw new PushError(
        'اتصال به سرویس اعلان مرورگر برقرار نشد. اتصال اینترنت را بررسی کن و دوباره تلاش کن.',
      );
    }
  }

  try {
    const { devices } = await apiFetch<{ devices: number }>(SUBSCRIPTIONS, {
      method: 'POST',
      accessToken: token,
      body: subscriptionBody(subscription),
    });
    return devices;
  } catch (cause) {
    // اشتراکی که سرور نپذیرفت در مرورگر نماند؛ وگرنه دکمه «روشن» نشان داده می‌شود
    // ولی اعلانی نمی‌رسد.
    await subscription.unsubscribe().catch(() => false);
    throw cause;
  }
}

/** خاموش‌کردن برای این مرورگر. خروجی: شمار دستگاه‌های باقی‌مانده. */
export async function disablePush(token: string): Promise<number> {
  const subscription = await currentSubscription();
  let devices = 0;
  if (subscription) {
    const result = await apiFetch<{ devices: number }>(
      `${SUBSCRIPTIONS}?endpoint=${encodeURIComponent(subscription.endpoint)}`,
      { method: 'DELETE', accessToken: token },
    );
    devices = result.devices;
    await subscription.unsubscribe().catch(() => false);
  }
  return devices;
}

/**
 * هنگام خروج: اشتراک این مرورگر از سرور و از مرورگر برداشته می‌شود.
 *
 * بهترین‌تلاش است و هرگز خروج را نمی‌بندد. اگر درخواست سرور شکست بخورد
 * (توکن منقضی، شبکه)، `unsubscribe()` مرورگر باز هم اجرا می‌شود؛ سرویس Push
 * از آن پس ۴۱۰ می‌دهد و سرور اشتراک را خودش پاک می‌کند.
 */
export async function releasePush(token: string | null): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  if (token) {
    await apiFetch(`${SUBSCRIPTIONS}?endpoint=${encodeURIComponent(subscription.endpoint)}`, {
      method: 'DELETE',
      accessToken: token,
    }).catch(() => undefined);
  }
  await subscription.unsubscribe().catch(() => false);
}
