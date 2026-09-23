/**
 * ارقام فارسی و لاتین — PRD §10.3 قاعدهٔ ۵.
 *
 * «اعداد در متن فارسی: فارسی. اعداد در جدول، کد و شناسه: لاتین.»
 */

const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'] as const;
const ARABIC_INDIC = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'] as const;

/** `1404` → `۱۴۰۴` — برای نمایش در متن فارسی. */
export function toPersianDigits(value: string | number): string {
  return String(value).replace(/\d/g, (d) => PERSIAN_DIGITS[Number(d)] ?? d);
}

/** `۱۴۰۴` → `1404` — برای ارسال به سرور و مقایسه. */
export function toLatinDigits(value: string): string {
  return value.replace(/[۰-۹٠-٩]/g, (ch) => {
    const persian = PERSIAN_DIGITS.indexOf(ch as (typeof PERSIAN_DIGITS)[number]);
    if (persian >= 0) return String(persian);
    const arabic = ARABIC_INDIC.indexOf(ch as (typeof ARABIC_INDIC)[number]);
    return arabic >= 0 ? String(arabic) : ch;
  });
}

/** جداکنندهٔ هزارگان فارسی: `1234567` → `۱٬۲۳۴٬۵۶۷`. */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('fa-IR').format(value);
}

/** مبلغ به ریال — PRD §4.0: پول همیشه BIGINT ریال است. */
export function formatRial(amountRial: number): string {
  return `${formatNumber(amountRial)} ریال`;
}

/**
 * عدد بزرگ به شکل کوتاه — برای کاشی آمار صفحهٔ اصلی (§10.10 «۴۶۰م»):
 * `460000000` → `۴۶۰ میلیون`، `1250000000` → `۱٫۳ میلیارد`.
 */
export function formatCompact(value: number): string {
  const units: [number, string][] = [
    [1_000_000_000, 'میلیارد'],
    [1_000_000, 'میلیون'],
    [1_000, 'هزار'],
  ];
  for (const [size, label] of units) {
    if (Math.abs(value) >= size) {
      const scaled = value / size;
      const rounded = scaled >= 100 ? Math.round(scaled) : Math.round(scaled * 10) / 10;
      return `${new Intl.NumberFormat('fa-IR').format(rounded)} ${label}`;
    }
  }
  return formatNumber(value);
}
