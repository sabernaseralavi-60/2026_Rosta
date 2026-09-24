'use client';

import * as Dialog from '@radix-ui/react-dialog';

import { Button } from '@/components/ui/Button';
import { toPersianDigits } from '@/lib/format/digits';

import { BadgeIcon } from './BadgeTile';

/**
 * جشن ارتقای سطح و نشان تازه — §9.10، §10.6 `LevelUpModal`.
 *
 * سه قاعده از §9.10 و §10.7:
 * * انیمیشن ≤ ۱٫۲ ثانیه (`--dur-celebrate` = ۹۰۰ms) و با
 *   `prefers-reduced-motion` عملاً حذف می‌شود.
 * * **همیشه قابل رد کردن** — Esc، کلیک بیرون، یا دکمه. «جشنی که مزاحم
 *   شود، دفعهٔ دوم آزاردهنده است.»
 * * فوکوس داخل مودال می‌ماند و پس از بستن برمی‌گردد (Radix Dialog).
 */

export type Celebration =
  | { kind: 'level'; level: number; title: string }
  | {
      kind: 'badge';
      code: string;
      title: string;
      description: string;
      icon: string;
      tier_fa: string;
    };

export interface LevelUpModalProps {
  celebration: Celebration | null;
  onClose: () => void;
}

export function LevelUpModal({ celebration, onClose }: LevelUpModalProps) {
  return (
    <Dialog.Root open={celebration !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[oklch(0%_0_0/0.45)]" />
        <Dialog.Content className="silp-celebrate fixed inset-x-0 top-1/2 z-50 mx-auto flex w-[min(92vw,380px)] -translate-y-1/2 flex-col items-center gap-4 rounded-[var(--radius-xl)] bg-[var(--bg-surface)] p-8 text-center shadow-[var(--shadow-lg)]">
          {celebration?.kind === 'level' && (
            <>
              <div
                aria-hidden="true"
                className="flex size-24 items-center justify-center rounded-[var(--radius-full)] bg-[var(--brand-50)] text-[40px] font-bold text-[var(--fg-brand)]"
              >
                {toPersianDigits(celebration.level)}
              </div>
              <Dialog.Title className="text-[22px] font-bold">
                به سطح {toPersianDigits(celebration.level)} رسیدی
              </Dialog.Title>
              <Dialog.Description className="text-[15px] text-[var(--fg-secondary)]">
                از این به بعد «{celebration.title}» هستی. ادامه بده.
              </Dialog.Description>
            </>
          )}
          {celebration?.kind === 'badge' && (
            <>
              <BadgeIcon icon={celebration.icon} earned size="lg" />
              <Dialog.Title className="text-[22px] font-bold">
                نشان «{celebration.title}» مال توست
              </Dialog.Title>
              <Dialog.Description className="text-[15px] text-[var(--fg-secondary)]">
                {celebration.description} — نشان {celebration.tier_fa}
              </Dialog.Description>
            </>
          )}
          <Dialog.Close asChild>
            <Button className="mt-2 w-full">ادامه</Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
