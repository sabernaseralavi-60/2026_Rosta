import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  disablePush,
  PushError,
  pushSupport,
  releasePush,
  subscriptionBody,
  urlBase64ToBytes,
} from '@/lib/push/client';

describe('urlBase64ToBytes', () => {
  it('decodes a VAPID public key to its 65 raw bytes', () => {
    // نقطهٔ فشرده‌نشدهٔ P-256: بایت اول ۴ و در کل ۶۵ بایت.
    const key = `B${'A'.repeat(86)}`;
    const bytes = urlBase64ToBytes(key);
    expect(bytes).toHaveLength(65);
    expect(bytes[0]).toBe(4);
  });

  it('accepts the URL-safe alphabet', () => {
    // `-` و `_` به `+` و `/` برمی‌گردند؛ atob با آن‌ها می‌شکند.
    expect(Array.from(urlBase64ToBytes('-_-_'))).toEqual(Array.from(urlBase64ToBytes('+/+/')));
  });

  it('works without padding', () => {
    expect(Array.from(urlBase64ToBytes('AQID'))).toEqual([1, 2, 3]);
    expect(Array.from(urlBase64ToBytes('AQI'))).toEqual([1, 2]);
  });
});

describe('subscriptionBody', () => {
  const fake = (json: Record<string, unknown>) =>
    ({ toJSON: () => json }) as unknown as PushSubscription;

  it('keeps only what the server needs', () => {
    expect(
      subscriptionBody(
        fake({
          endpoint: 'https://fcm.googleapis.com/fcm/send/x',
          expirationTime: null,
          keys: { p256dh: 'P', auth: 'A' },
        }),
      ),
    ).toEqual({
      endpoint: 'https://fcm.googleapis.com/fcm/send/x',
      keys: { p256dh: 'P', auth: 'A' },
    });
  });

  it('refuses a subscription without keys', () => {
    expect(() => subscriptionBody(fake({ endpoint: 'https://fcm.googleapis.com/x' }))).toThrow(
      PushError,
    );
    expect(() => subscriptionBody(fake({ endpoint: 'https://x', keys: { p256dh: 'P' } }))).toThrow(
      PushError,
    );
  });
});

describe('pushSupport', () => {
  it('is unsupported where there is no service worker (jsdom)', () => {
    expect(pushSupport()).toBe('unsupported');
  });
});

describe('leaving a shared computer', () => {
  const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/dev 1';
  const unsubscribe = vi.fn();
  let fetchMock: ReturnType<typeof vi.fn>;

  function installBrowser(subscription: unknown) {
    Object.defineProperty(window, 'PushManager', { value: class {}, configurable: true });
    Object.defineProperty(window, 'Notification', {
      value: { permission: 'granted' },
      configurable: true,
    });
    Object.defineProperty(navigator, 'serviceWorker', {
      value: {
        ready: Promise.resolve({ pushManager: { getSubscription: async () => subscription } }),
      },
      configurable: true,
    });
  }

  beforeEach(() => {
    unsubscribe.mockReset().mockResolvedValue(true);
    fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ devices: 0 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    installBrowser({ endpoint: ENDPOINT, unsubscribe });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(window, 'PushManager');
    Reflect.deleteProperty(window, 'Notification');
    Reflect.deleteProperty(navigator, 'serviceWorker');
  });

  it('removes this browser from the server and from the browser', async () => {
    await releasePush('token-1');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('DELETE');
    expect(url).toContain(`endpoint=${encodeURIComponent(ENDPOINT)}`);
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer token-1');
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it('still unsubscribes the browser when the server call fails (expired token, offline)', async () => {
    fetchMock.mockRejectedValue(new TypeError('offline'));
    await expect(releasePush('expired')).resolves.toBeUndefined();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it('skips the server call without a token but still unsubscribes', async () => {
    await releasePush(null);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it('does nothing on a browser that never subscribed', async () => {
    installBrowser(null);
    await releasePush('token-1');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('turning it off here reports how many devices remain', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ devices: 2 }), { status: 200 }));
    expect(await disablePush('token-1')).toBe(2);
    expect(unsubscribe).toHaveBeenCalledOnce();
  });
});
