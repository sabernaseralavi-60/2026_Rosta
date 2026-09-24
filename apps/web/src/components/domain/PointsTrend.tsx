'use client';

import { useState } from 'react';

import { points, type TrendPoint } from '@/lib/api/points';
import { formatDateLong } from '@/lib/format/date';
import { formatNumber } from '@/lib/format/digits';

/**
 * روند امتیاز نیم‌سال — FR-DASH-01 «نمودار روند امتیاز در نیم‌سال».
 *
 * یک سری، تغییر در زمان ⇒ ستون هفتگی با **یک رنگ** (برند). بدون جعبهٔ
 * راهنما: عنوان می‌گوید چه رسم شده. مشخصات علامت از راهنمای داده‌نمایی:
 *
 * * ستون ≤ ۲۴px، سر گرد ۴px، پایهٔ صاف روی خط مبنا؛ فاصلهٔ ۲px سطح.
 * * برچسب مستقیم فقط روی هفتهٔ جاری — نه عدد روی هر ستون.
 * * هاور روی هر ستون، ناحیهٔ لمس کل ارتفاع ستون (نه فقط خود ستون)؛ کیبورد
 *   با یک توقف Tab و فلش.
 * * جدول معادل برای صفحه‌خوان — نمودار تنها حامل عدد نیست.
 *
 * هفتهٔ منفی (اصلاح امتیاز) زیر خط مبنا و خاکستری است، نه قرمز: «احترام
 * به کاهش» (§9.10) — کاهش دیده می‌شود ولی هشدار نمی‌دهد.
 */

const WIDTH = 600;
const HEIGHT = 160;
const PAD_TOP = 22;
const PAD_BOTTOM = 22;
const MAX_BAR = 24;
const GAP = 2;
const RADIUS = 4;

export function PointsTrend({ trend }: { trend: TrendPoint[] }) {
  const [active, setActive] = useState<number | null>(null);
  if (trend.length === 0) return null;

  const values = trend.map((t) => points(t.total));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const y = (value: number) => PAD_TOP + ((max - value) / span) * plotHeight;
  const baseline = y(0);
  const band = WIDTH / trend.length;
  const barWidth = Math.min(MAX_BAR, band - GAP);
  const last = trend.length - 1;
  const hovered = active ?? null;

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-[13px] text-[var(--fg-secondary)]">
        امتیاز هفتگی در {formatNumber(trend.length)} هفتهٔ اخیر
      </figcaption>
      <div className="relative">
        {/* یک توقف Tab برای کل نمودار، نه یکی برای هر ستون: صفحه‌خوان عددها
            را از جدول پایین می‌خواند، و کاربر بینای کیبورد با فلش بین هفته‌ها
            جابه‌جا می‌شود (M7-14). محور زمان چپ‌به‌راست است، پس فلش راست
            یعنی هفتهٔ بعد، حتی در صفحهٔ راست‌چین. */}
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-40 w-full rounded-[var(--radius-sm)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]"
          role="img"
          aria-label="نمودار ستونی امتیاز هفتگی؛ عددها در جدول بعدی"
          tabIndex={0}
          onFocus={() => setActive((current) => current ?? last)}
          onBlur={() => setActive(null)}
          onKeyDown={(event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            event.preventDefault();
            const step = event.key === 'ArrowRight' ? 1 : -1;
            setActive((current) => Math.max(0, Math.min(last, (current ?? last) + step)));
          }}
          onMouseLeave={() => setActive(null)}
        >
          <line
            x1={0}
            x2={WIDTH}
            y1={baseline}
            y2={baseline}
            stroke="var(--border-subtle)"
            strokeWidth={1}
          />
          {trend.map((point, index) => {
            const value = values[index] ?? 0;
            const cx = band * index + band / 2;
            const x = cx - barWidth / 2;
            const top = Math.min(y(value), baseline);
            const height = Math.abs(y(value) - baseline);
            const positive = value >= 0;
            return (
              <g key={point.week_start} onMouseEnter={() => setActive(index)}>
                {/* ناحیهٔ هدف: کل ارتفاع نوار، بزرگ‌تر از خود ستون. */}
                <rect x={band * index} y={0} width={band} height={HEIGHT} fill="transparent" />
                {height > 0 && (
                  <path
                    d={barPath(x, top, barWidth, height, positive)}
                    fill={positive ? 'var(--brand-600)' : 'var(--neutral-400)'}
                    opacity={hovered === null || hovered === index ? 1 : 0.55}
                  />
                )}
                {index === last && (
                  <text
                    x={cx}
                    y={positive ? top - 6 : top + height + 14}
                    textAnchor="middle"
                    fontSize={12}
                    fill="var(--fg-secondary)"
                  >
                    {formatNumber(value)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {hovered !== null && trend[hovered] && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-0 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-2.5 py-1.5 text-[12.5px] shadow-[var(--shadow-md)]"
            style={{
              // در RTL، نمودار از چپ به راست زمانی است (محور زمان جهت‌دار نیست).
              left: `${((hovered + 0.5) / trend.length) * 100}%`,
              transform: 'translateX(-50%)',
            }}
          >
            <div className="text-[var(--fg-tertiary)]">
              هفتهٔ {formatDateLong(trend[hovered].week_start)}
            </div>
            <div className="font-semibold text-[var(--fg-primary)]">
              {formatNumber(values[hovered] ?? 0)} امتیاز
            </div>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>امتیاز هفتگی</caption>
        <thead>
          <tr>
            <th scope="col">آغاز هفته</th>
            <th scope="col">امتیاز</th>
          </tr>
        </thead>
        <tbody>
          {trend.map((point, index) => (
            <tr key={point.week_start}>
              <td>{formatDateLong(point.week_start)}</td>
              <td>{formatNumber(values[index] ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** ستون با سر گرد ۴px و پایهٔ صاف — سر همیشه دور از خط مبنا. */
function barPath(x: number, top: number, width: number, height: number, up: boolean): string {
  const r = Math.min(RADIUS, width / 2, height);
  if (up) {
    const bottom = top + height;
    return [
      `M${x},${bottom}`,
      `V${top + r}`,
      `Q${x},${top} ${x + r},${top}`,
      `H${x + width - r}`,
      `Q${x + width},${top} ${x + width},${top + r}`,
      `V${bottom}`,
      'Z',
    ].join(' ');
  }
  const bottom = top + height;
  return [
    `M${x},${top}`,
    `V${bottom - r}`,
    `Q${x},${bottom} ${x + r},${bottom}`,
    `H${x + width - r}`,
    `Q${x + width},${bottom} ${x + width},${bottom - r}`,
    `V${top}`,
    'Z',
  ].join(' ');
}
