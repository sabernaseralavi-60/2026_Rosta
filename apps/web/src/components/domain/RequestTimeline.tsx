import { Badge } from '@/components/ui/Badge';
import { type IntakeEvent, type IntakeStatus, STATUS_TONES } from '@/lib/api/inbox';
import { formatDateTime } from '@/lib/format/date';

/**
 * تاریخچهٔ رسیدگی به یک درخواست — هم برای مالک و هم برای مشتری (ADR-0032).
 *
 * خودِ کامپوننت فقط `public_note` را می‌شناسد؛ یادداشت خصوصی مالک اصلاً به آن نمی‌رسد.
 * `labels` تعیین می‌کند «جدید» برای چه کسی چه بخواند: مالک «جدید»، مشتری «دریافت شد».
 */
export function RequestTimeline({
  createdAt,
  events,
  labels,
}: {
  createdAt: string;
  events: IntakeEvent[];
  labels: Record<IntakeStatus, string>;
}) {
  return (
    <ol className="flex flex-col gap-3 border-s-2 border-[var(--border-subtle)] ps-4">
      <li className="flex flex-col gap-0.5">
        <span className="text-[13.5px] font-medium">ثبت شد</span>
        <time className="text-[12.5px] text-[var(--fg-tertiary)]" dateTime={createdAt}>
          {formatDateTime(createdAt)}
        </time>
      </li>
      {events.map((event) => (
        <li key={event.id} className="flex flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2 text-[13.5px] font-medium">
            <Badge tone={STATUS_TONES[event.to_status]}>{labels[event.to_status]}</Badge>
            {event.from_status === event.to_status && (
              <span className="text-[12.5px] font-normal text-[var(--fg-secondary)]">
                پیام تازه
              </span>
            )}
          </span>
          {event.public_note && (
            <p className="max-w-[62ch] whitespace-pre-line text-[14px] leading-[1.9]">
              {event.public_note}
            </p>
          )}
          <time className="text-[12.5px] text-[var(--fg-tertiary)]" dateTime={event.created_at}>
            {formatDateTime(event.created_at)}
          </time>
        </li>
      ))}
    </ol>
  );
}
