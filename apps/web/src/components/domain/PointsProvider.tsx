'use client';

import * as Toast from '@radix-ui/react-toast';
import dynamic from 'next/dynamic';
import { usePathname } from 'next/navigation';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

import { WRITE_EVENT } from '@/lib/api/client';
import {
  type Badge,
  fetchBadges,
  fetchPointsSummary,
  markBadgesSeen,
  type PointEntry,
  type PointsSummary,
} from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { formatNumber } from '@/lib/format/digits';
import {
  freshAwards,
  lastSeenEntry,
  lastSeenLevel,
  rememberEntry,
  rememberLevel,
} from '@/lib/points/memory';

import type { Celebration } from './LevelUpModal';

// جشن سطح و نشان چند بار در نیم‌سال رخ می‌دهد، ولی Radix Dialog و خودش در
// JS اولیهٔ همهٔ صفحه‌ها بودند. فقط وقتی جشنی هست بار می‌شود (M7-15).
const LevelUpModal = dynamic(() => import('./LevelUpModal').then((m) => m.LevelUpModal), {
  ssr: false,
});

/**
 * حالت امتیاز پوستهٔ اپلیکیشن — §9.10.
 *
 * | اصل §9.10 | اینجا |
 * |-----------|-------|
 * | فوریت | پس از هر نوشتن موفق (`WRITE_EVENT`) خلاصه دوباره خوانده و امتیاز تازه Toast می‌شود |
 * | پیشرفت | خلاصه به `PointsBadge` هدر داده می‌شود |
 * | جشن | سطح بالاتر یا نشان تازه ⇒ مودال |
 * | احترام به کاهش | Toast فقط برای امتیاز مثبت (`freshAwards`) |
 *
 * نشان‌ها با کار پس‌زمینه اعطا می‌شوند (§9.5، هر ۱۰ دقیقه)، پس دنبالشان
 * پس از هر نوشتن نمی‌گردیم — در بارگذاری و وقتی کاربر به تب برمی‌گردد.
 */

const REFRESH_DEBOUNCE_MS = 600;
const BADGE_CHECK_INTERVAL_MS = 5 * 60_000;

interface PointsContextValue {
  summary: PointsSummary | null;
}

const PointsContext = createContext<PointsContextValue>({ summary: null });

export function usePoints(): PointsContextValue {
  return useContext(PointsContext);
}

interface ToastItem {
  key: string;
  entry: PointEntry;
}

export function PointsProvider({ children }: { children: ReactNode }) {
  const { session, accessToken } = useSession({ required: false });
  const userId = session?.user.id ?? null;
  const pathname = usePathname();

  const [summary, setSummary] = useState<PointsSummary | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [queue, setQueue] = useState<Celebration[]>([]);
  const badgeCheckedAt = useRef(0);

  const refresh = useCallback(async () => {
    if (!accessToken || !userId) return;
    let next: PointsSummary;
    try {
      next = await fetchPointsSummary(accessToken);
    } catch {
      return; // هدر بدون امتیاز بهتر از هدر شکسته است.
    }
    setSummary(next);

    const fresh = freshAwards(next.recent, lastSeenEntry(userId));
    if (fresh.length > 0) {
      setToasts((current) => [...current, ...fresh.map((entry) => ({ key: entry.id, entry }))]);
    }
    if (next.latest_entry_id) rememberEntry(userId, next.latest_entry_id);

    const knownLevel = lastSeenLevel(userId);
    if (knownLevel !== null && next.level.level > knownLevel) {
      setQueue((current) => [
        ...current,
        { kind: 'level', level: next.level.level, title: next.level.title_fa },
      ]);
    }
    rememberLevel(userId, next.level.level);
  }, [accessToken, userId]);

  const checkBadges = useCallback(async () => {
    if (!accessToken) return;
    if (Date.now() - badgeCheckedAt.current < BADGE_CHECK_INTERVAL_MS) return;
    badgeCheckedAt.current = Date.now();
    let unseen: Badge[];
    try {
      unseen = (await fetchBadges(accessToken)).earned.filter((badge) => !badge.seen);
    } catch {
      return;
    }
    if (unseen.length === 0) return;
    setQueue((current) => [
      ...current,
      ...unseen.map((badge): Celebration => ({
        kind: 'badge',
        code: badge.code,
        title: badge.title_fa,
        description: badge.description,
        icon: badge.icon,
        tier_fa: badge.tier_fa,
      })),
    ]);
  }, [accessToken]);

  // بارگذاری اول و هر جابه‌جایی صفحه — ارسال آزمون به صفحهٔ نتیجه می‌رود.
  useEffect(() => {
    void refresh();
  }, [refresh, pathname]);

  useEffect(() => {
    void checkBadges();
  }, [checkBadges]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onWrite = () => {
      clearTimeout(timer);
      timer = setTimeout(() => void refresh(), REFRESH_DEBOUNCE_MS);
    };
    const onFocus = () => {
      void refresh();
      void checkBadges();
    };
    window.addEventListener(WRITE_EVENT, onWrite);
    window.addEventListener('focus', onFocus);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(WRITE_EVENT, onWrite);
      window.removeEventListener('focus', onFocus);
    };
  }, [refresh, checkBadges]);

  const current = queue[0] ?? null;
  const closeCelebration = useCallback(() => {
    if (current?.kind === 'badge' && accessToken) {
      void markBadgesSeen(accessToken, [current.code]).catch(() => undefined);
    }
    setQueue((items) => items.slice(1));
  }, [current, accessToken]);

  return (
    <PointsContext.Provider value={{ summary }}>
      <Toast.Provider swipeDirection="up" duration={4000} label="امتیاز">
        {children}
        {toasts.map(({ key, entry }) => (
          <Toast.Root
            key={key}
            className="silp-toast flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-4 py-3 shadow-[var(--shadow-lg)]"
            onOpenChange={(open) => {
              if (!open) setToasts((items) => items.filter((item) => item.key !== key));
            }}
          >
            <Toast.Title className="text-[15px] font-bold text-[var(--fg-brand)]">
              +{formatNumber(Number(entry.amount))} امتیاز
            </Toast.Title>
            <Toast.Description className="text-[13.5px] text-[var(--fg-secondary)]">
              {entry.rule_title_fa}
            </Toast.Description>
          </Toast.Root>
        ))}
        {/* §10.6 — حداکثر ۳ هم‌زمان، بالا-وسط. */}
        {/* کلید میان‌بر جدا از اعلان‌ها (F8)؛ با یک کلید، فوکوس بین دو ناحیه
            گم می‌شد. */}
        <Toast.Viewport
          label="امتیازهای تازه ({hotkey})"
          hotkey={['F9']}
          className="fixed inset-x-0 top-4 z-50 mx-auto flex w-[min(92vw,360px)] flex-col gap-2 outline-none"
        />
      </Toast.Provider>
      {current && <LevelUpModal celebration={current} onClose={closeCelebration} />}
    </PointsContext.Provider>
  );
}
