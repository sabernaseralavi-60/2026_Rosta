import katex from 'katex';

/**
 * فرمول ریاضی برای مطالب علمی — ADR-0030.
 *
 * KaTeX سمت سرور، هنگام رندر صفحه اجرا می‌شود و HTML آماده می‌دهد؛ هیچ JS
 * فرمولی به مرورگر نمی‌رود. ورودی از یادداشت‌های خود مالک است، ولی باز هم
 * `trust: false` (پیش‌فرض) می‌ماند و `\href`، `\url` و `\includegraphics`
 * کار نمی‌کنند. فرمول خراب خطا نمی‌اندازد؛ همان متن خام قرمز نشان داده می‌شود
 * (`throwOnError: false`) تا یک فرمول اشتباه کل مطلب را از دسترس نبرد.
 */
function toHtml(source: string, display: boolean): string {
  return katex.renderToString(source, {
    displayMode: display,
    throwOnError: false,
    strict: 'ignore',
    output: 'htmlAndMathml',
  });
}

/** فرمول بلوکی (`$$ … $$`): وسط‌چین، چپ‌به‌راست، با اسکرول افقی در موبایل. */
export function MathBlock({ source }: { source: string }) {
  return (
    <div
      dir="ltr"
      role="math"
      className="overflow-x-auto py-2 text-[1.05em]"
      // eslint-disable-next-line react/no-danger -- خروجی KaTeX با trust:false
      dangerouslySetInnerHTML={{ __html: toHtml(source, true) }}
    />
  );
}

/** فرمول درون‌خطی (`$ … $`). */
export function MathInline({ source }: { source: string }) {
  return (
    <span
      dir="ltr"
      className="inline-block align-middle"
      // eslint-disable-next-line react/no-danger -- خروجی KaTeX با trust:false
      dangerouslySetInnerHTML={{ __html: toHtml(source, false) }}
    />
  );
}
