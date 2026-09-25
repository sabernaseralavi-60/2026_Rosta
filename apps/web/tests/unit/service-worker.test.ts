import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';

import { describe, expect, it, vi } from 'vitest';

/**
 * سرویس‌کارگر — `public/sw.js`.
 *
 * فایل ساخته نمی‌شود و ماژول نیست؛ همان متن را در یک `vm` با `self` ساختگی
 * اجرا می‌کنیم تا رفتار واقعی‌اش (نه بازنویسی آن) آزموده شود.
 */

const SOURCE = readFileSync(join(__dirname, '../../public/sw.js'), 'utf8');
const ORIGIN = 'https://silp.example';

interface FakeClient {
  url: string;
  visibilityState: 'visible' | 'hidden';
  focused: boolean;
  focus: ReturnType<typeof vi.fn>;
  navigate: ReturnType<typeof vi.fn>;
}

function client(overrides: Partial<FakeClient> = {}): FakeClient {
  return {
    url: `${ORIGIN}/dashboard`,
    visibilityState: 'hidden',
    focused: false,
    focus: vi.fn().mockResolvedValue(undefined),
    navigate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

type Handler = (event: unknown) => void;

/** اولین فراخوانی یک mock؛ اگر نبود تست با پیام روشن می‌شکند. */
interface Shown {
  body: string;
  dir: string;
  lang: string;
  data: { url: string };
  requireInteraction: boolean;
}

function firstCall(mock: ReturnType<typeof vi.fn>): [string, Shown] {
  const call = mock.mock.calls[0];
  if (!call) throw new Error('mock was never called');
  return call as [string, Shown];
}

function boot(windows: FakeClient[] = []) {
  const handlers: Record<string, Handler> = {};
  const showNotification = vi.fn().mockResolvedValue(undefined);
  const openWindow = vi.fn().mockResolvedValue(undefined);
  const cacheAdd = vi.fn().mockResolvedValue(undefined);
  const caches = {
    open: vi.fn().mockResolvedValue({ add: cacheAdd }),
    keys: vi.fn().mockResolvedValue([]),
    match: vi.fn().mockResolvedValue('OFFLINE'),
    delete: vi.fn(),
  };
  const fetchMock = vi.fn();
  const scope = {
    location: { origin: ORIGIN },
    addEventListener: (name: string, fn: Handler) => {
      handlers[name] = fn;
    },
    skipWaiting: vi.fn(),
    registration: { showNotification },
    clients: {
      matchAll: vi.fn().mockResolvedValue(windows),
      openWindow,
      claim: vi.fn(),
    },
  };
  const context = vm.createContext({
    self: scope,
    caches,
    URL,
    Response: { error: () => 'NETWORK_ERROR' },
    fetch: fetchMock,
    console,
  });
  vm.runInContext(SOURCE, context);
  const fire = (name: string, e: unknown) => {
    const handler = handlers[name];
    if (!handler) throw new Error(`no ${name} listener registered`);
    handler(e);
  };
  return { fire, showNotification, openWindow, caches, fetchMock };
}

/** رویداد با `waitUntil` که کار را نگه می‌دارد تا تست منتظرش بماند. */
function event<T extends object>(extra: T) {
  let work: Promise<unknown> = Promise.resolve();
  return {
    ...extra,
    waitUntil: (p: Promise<unknown>) => {
      work = p;
    },
    done: () => work,
  };
}

const pushEvent = (payload: unknown) =>
  event({ data: { json: () => payload, text: () => String(payload) } });

describe('service worker: push', () => {
  it('shows the notification with an internal url and Persian direction', async () => {
    const { fire, showNotification } = boot();
    const e = pushEvent({ title: 'نتیجهٔ آزمون', body: 'نمره‌ات ثبت شد.', url: '/quiz/1' });
    fire('push', e);
    await e.done();

    const [title, options] = firstCall(showNotification);
    expect(title).toBe('نتیجهٔ آزمون');
    expect(options).toMatchObject({
      body: 'نمره‌ات ثبت شد.',
      dir: 'rtl',
      lang: 'fa',
      data: { url: '/quiz/1' },
      requireInteraction: false,
    });
  });

  it('keeps urgent notifications on screen until touched', async () => {
    const { fire, showNotification } = boot();
    const e = pushEvent({ title: 'فوری', body: 'x', url: '/a', urgent: true });
    fire('push', e);
    await e.done();
    expect(firstCall(showNotification)[1].requireInteraction).toBe(true);
  });

  it('stays quiet while the user is looking at the site (SSE already showed it)', async () => {
    const { fire, showNotification } = boot([
      client({ visibilityState: 'visible', focused: true }),
    ]);
    const e = pushEvent({ title: 't', body: 'b', url: '/x' });
    fire('push', e);
    await e.done();
    expect(showNotification).not.toHaveBeenCalled();
  });

  it('still shows it when the site is open but in the background', async () => {
    const { fire, showNotification } = boot([client({ visibilityState: 'hidden' })]);
    const e = pushEvent({ title: 't', body: 'b', url: '/x' });
    fire('push', e);
    await e.done();
    expect(showNotification).toHaveBeenCalledOnce();
  });

  it.each([
    ['https://evil.example/phish', '/notifications'],
    ['//evil.example/phish', '/notifications'],
    ['/\\evil.example', '/notifications'],
    ['javascript:alert(1)', '/notifications'],
    [undefined, '/notifications'],
    [42, '/notifications'],
    ['/projects/p1/workspace?tab=x', '/projects/p1/workspace?tab=x'],
  ])('never trusts a payload url: %s', async (url, expected) => {
    const { fire, showNotification } = boot();
    const e = pushEvent({ title: 't', body: 'b', url });
    fire('push', e);
    await e.done();
    expect(firstCall(showNotification)[1].data.url).toBe(expected);
  });

  it('survives a payload that is not JSON', async () => {
    const { fire, showNotification } = boot();
    const e = event({
      data: {
        json: () => {
          throw new SyntaxError('not json');
        },
        text: () => 'سلام',
      },
    });
    fire('push', e);
    await e.done();
    const [title, options] = firstCall(showNotification);
    expect(title).toBe('سابِر');
    expect(options.body).toBe('سلام');
  });

  it('survives a push with no data at all', async () => {
    const { fire, showNotification } = boot();
    const e = event({ data: null });
    fire('push', e);
    await e.done();
    expect(showNotification).toHaveBeenCalledOnce(); // Chrome: هر push باید اعلانی بسازد
  });
});

describe('service worker: notification click', () => {
  const click = (url: unknown) => {
    const close = vi.fn();
    return { close, ...event({ notification: { close, data: { url } } }) };
  };

  it('focuses and navigates an open tab of the site', async () => {
    const tab = client({ url: `${ORIGIN}/dashboard` });
    const { fire, openWindow } = boot([tab]);
    const e = click('/quiz/1');
    fire('notificationclick', e);
    await e.done();

    expect(e.close).toHaveBeenCalled();
    expect(tab.focus).toHaveBeenCalled();
    expect(tab.navigate).toHaveBeenCalledWith(`${ORIGIN}/quiz/1`);
    expect(openWindow).not.toHaveBeenCalled();
  });

  it('opens a new window when no tab is open', async () => {
    const { fire, openWindow } = boot([]);
    const e = click('/quiz/1');
    fire('notificationclick', e);
    await e.done();
    expect(openWindow).toHaveBeenCalledWith(`${ORIGIN}/quiz/1`);
  });

  it('ignores tabs of other origins', async () => {
    const other = client({ url: 'https://other.example/x' });
    const { fire, openWindow } = boot([other]);
    const e = click('/quiz/1');
    fire('notificationclick', e);
    await e.done();
    expect(other.focus).not.toHaveBeenCalled();
    expect(openWindow).toHaveBeenCalled();
  });

  it('falls back to a new window if the tab cannot be navigated', async () => {
    const tab = client({ navigate: vi.fn().mockRejectedValue(new Error('not controlled')) });
    const { fire, openWindow } = boot([tab]);
    const e = click('/quiz/1');
    fire('notificationclick', e);
    await e.done();
    expect(openWindow).toHaveBeenCalledWith(`${ORIGIN}/quiz/1`);
  });

  it('never opens a foreign url even if the stored data was tampered with', async () => {
    const { fire, openWindow } = boot([]);
    const e = click('https://evil.example/phish');
    fire('notificationclick', e);
    await e.done();
    expect(openWindow).toHaveBeenCalledWith(`${ORIGIN}/notifications`);
  });
});

describe('service worker: offline shell', () => {
  it('precaches only the static offline page', async () => {
    const { fire, caches } = boot();
    const e = event({});
    fire('install', e);
    await e.done();
    expect(caches.open).toHaveBeenCalledWith('silp-shell-v1');
    const opened = await caches.open.mock.results[0]?.value;
    expect(opened.add).toHaveBeenCalledWith('/offline.html');
    expect(opened.add).toHaveBeenCalledOnce();
  });

  it('answers a failed navigation with the offline page', async () => {
    const { fire, fetchMock } = boot();
    fetchMock.mockRejectedValue(new TypeError('offline'));
    let response: Promise<unknown> | undefined;
    fire('fetch', {
      request: { mode: 'navigate' },
      respondWith: (p: Promise<unknown>) => {
        response = p;
      },
    });
    expect(await response).toBe('OFFLINE');
  });

  it('does not touch API calls or assets', () => {
    const { fire } = boot();
    const respondWith = vi.fn();
    fire('fetch', { request: { mode: 'cors' }, respondWith });
    fire('fetch', { request: { mode: 'no-cors' }, respondWith });
    expect(respondWith).not.toHaveBeenCalled();
  });
});
