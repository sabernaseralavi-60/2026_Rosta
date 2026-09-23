'use client';

import * as Toast from '@radix-ui/react-toast';
import Link from 'next/link';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  type AppNotification,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  readNotificationStream,
} from '@/lib/api/notifications';
import { useSession } from '@/lib/auth/use-session';

/**
 * حالت اعلان پوستهٔ اپلیکیشن — FR-MSG-01، M6-08.
 *
 * | کار | اینجا |
 * |-----|-------|
 * | شمارندهٔ زنگوله | از رویداد `unread` جریان SSE |
 * | اعلان تازه | رویداد `notification` ⇒ `version` بالا می‌رود تا فهرست باز دوباره بخواند |
 * | مهم و فوری | Toast پایین صفحه، با `aria-live` |
 * | قطع جریان | هر ۱۰ دقیقه سرور می‌بندد ⇒ اتصال دوباره. شکست ⇒ عقب‌نشینی تا ۶۰ ثانیه و در این فاصله پرسش شمارنده |
 *
 * جریان روی پروکسی‌ای که پاسخ را بافر کند اصلاً نمی‌رسد؛ پرسش دوره‌ای
 * تضمین می‌کند زنگوله در بدترین حالت هم دقیقه‌ای یک بار درست شود.
 */

const RETRY_BASE_MS = 3_000;
const RETRY_MAX_MS = 60_000;
const TOAST_PRIORITIES = new Set(['IMPORTANT', 'URGENT']);

interface NotificationsContextValue {
  unread: number | null;
  /** با هر اعلان تازه یا تغییر وضعیت خواندن بالا می‌رود. */
  version: number;
  markRead: (notification: AppNotification) => Promise<void>;
  markAllRead: () => Promise<void>;
}

const NotificationsContext = createContext<NotificationsContextValue>({
  unread: null,
  version: 0,
  markRead: async () => undefined,
  markAllRead: async () => undefined,
});

export function useNotifications(): NotificationsContextValue {
  return useContext(NotificationsContext);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useSession({ required: false });
  const [unread, setUnread] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<AppNotification[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    const { signal } = controller;

    const refreshCount = async () => {
      try {
        setUnread(await fetchUnreadCount(accessToken));
      } catch {
        // زنگولهٔ بی‌عدد بهتر از هدر شکسته است.
      }
    };

    void (async () => {
      let failures = 0;
      await refreshCount();
      while (!signal.aborted) {
        try {
          await readNotificationStream(
            accessToken,
            {
              onUnread: (count) => {
                failures = 0;
                setUnread(count);
              },
              onNotification: (notification) => {
                setVersion((v) => v + 1);
                if (TOAST_PRIORITIES.has(notification.priority)) {
                  setToasts((current) => [...current.slice(-2), notification]);
                }
              },
            },
            signal,
          );
        } catch {
          if (signal.aborted) return;
          failures += 1;
        }
        if (signal.aborted) return;
        const delay = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** Math.max(0, failures - 1));
        if (failures > 0) await refreshCount();
        await sleep(failures > 0 ? delay : 500, signal);
      }
    })();

    return () => controller.abort();
  }, [accessToken]);

  const markRead = useCallback(
    async (notification: AppNotification) => {
      if (!accessToken || notification.is_read) return;
      await markNotificationRead(accessToken, notification.id);
      setUnread((count) => (count === null ? count : Math.max(0, count - 1)));
      setVersion((v) => v + 1);
    },
    [accessToken],
  );

  const markAllRead = useCallback(async () => {
    if (!accessToken) return;
    await markAllNotificationsRead(accessToken);
    setUnread(0);
    setVersion((v) => v + 1);
  }, [accessToken]);

  const value = useMemo(
    () => ({ unread, version, markRead, markAllRead }),
    [unread, version, markRead, markAllRead],
  );

  return (
    <NotificationsContext.Provider value={value}>
      <Toast.Provider swipeDirection="down" duration={7000} label="اعلان">
        {children}
        {toasts.map((notification) => (
          <Toast.Root
            key={notification.id}
            className="silp-toast flex flex-col gap-1 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-4 py-3 shadow-[var(--shadow-lg)]"
            onOpenChange={(open) => {
              if (!open) setToasts((items) => items.filter((item) => item.id !== notification.id));
            }}
          >
            <Toast.Title className="text-[14.5px] font-semibold text-[var(--fg-primary)]">
              {notification.title}
            </Toast.Title>
            <Toast.Description className="line-clamp-2 text-[13px] text-[var(--fg-secondary)]">
              {notification.body}
            </Toast.Description>
            {notification.action_url && (
              <Toast.Action altText="مشاهده" asChild>
                <Link
                  href={notification.action_url}
                  className="self-start text-[13px] font-medium text-[var(--brand-700)] hover:underline"
                >
                  مشاهده
                </Link>
              </Toast.Action>
            )}
          </Toast.Root>
        ))}
        {/* پایین صفحه — بالای صفحه مال Toast امتیاز است (§10.6). */}
        <Toast.Viewport className="fixed inset-x-0 bottom-4 z-50 mx-auto flex w-[min(92vw,380px)] flex-col gap-2 outline-none" />
      </Toast.Provider>
    </NotificationsContext.Provider>
  );
}
