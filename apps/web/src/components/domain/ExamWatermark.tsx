'use client';

/**
 * واترمارک پویای حالت آزمون — ADR-0036 §۴.
 *
 * نام دانشجو و ساعت، کم‌رنگ و مورب روی کل صفحه تکرار می‌شود تا عکس یا اسکرین‌شاتِ
 * سؤال به صاحبش برگردد. بازدارندهٔ اجتماعی است، نه قفل فنی؛ پس رویدادهای ماوس را نمی‌گیرد
 * و متن را نمی‌پوشاند (`pointer-events: none`، شفافیت کم). متن با DOM/CSS است، نه Canvas:
 * Canvas فارسی را می‌شکند و ارزش امنیتی‌ای هم نمی‌افزاید.
 */
export function ExamWatermark({ label }: { label: string }) {
  const stamp = new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(),
  );
  const text = `${label} · ${stamp}`;
  return (
    <div
      aria-hidden="true"
      data-testid="exam-watermark"
      className="pointer-events-none fixed inset-0 z-30 select-none overflow-hidden"
    >
      <div className="absolute -inset-1/2 flex -rotate-[24deg] flex-col justify-center gap-16 opacity-[0.07]">
        {Array.from({ length: 14 }, (_, row) => (
          <div key={row} className="flex gap-16 whitespace-nowrap text-[22px] font-bold">
            {Array.from({ length: 8 }, (_, col) => (
              <span key={col}>{text}</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
