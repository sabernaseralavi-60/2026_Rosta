import Image from 'next/image';

import { externalCover, PHOTOS, photoKeyFor } from '@/lib/photos';

/**
 * تصویر روی‌جلد یک محتوا: کلید عکس ثبت‌شدهٔ سایت، نشانی https بیرونی، یا عکس
 * پیش‌فرض نوع. عکس‌های سایت با بهینه‌ساز Next سرو می‌شوند؛ نشانی بیرونی
 * دست‌نخورده می‌ماند (دامنه‌اش در `next.config` ثبت نیست).
 */
export function CoverImage({
  cover,
  kind,
  sizes,
  priority = false,
  className = '',
}: {
  cover: string | null;
  kind: string;
  sizes: string;
  priority?: boolean;
  className?: string;
}) {
  const external = externalCover(cover);
  if (external) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- نشانی بیرونی، خارج از بهینه‌ساز
      <img
        src={external}
        alt=""
        loading={priority ? 'eager' : 'lazy'}
        className={`absolute inset-0 size-full object-cover ${className}`}
      />
    );
  }
  const photo = PHOTOS[photoKeyFor(cover, kind)];
  return (
    <Image
      src={photo.src}
      alt=""
      fill
      sizes={sizes}
      priority={priority}
      className={`object-cover ${className}`}
    />
  );
}
