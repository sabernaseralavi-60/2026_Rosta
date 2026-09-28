/** فقط پیوندهای داخلی و https در متن مطلب زنده می‌مانند؛ بقیه به متن ساده تبدیل می‌شوند. */
export function resolveContentLink(href: string): string | null {
  if (href.startsWith('/') && !href.startsWith('//')) return href;
  if (href.startsWith('#') || href.startsWith('https://')) return href;
  return null;
}
