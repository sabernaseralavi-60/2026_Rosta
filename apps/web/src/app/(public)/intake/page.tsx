import type { Metadata } from 'next';
import Image from 'next/image';

import { IntakeForm } from '@/components/public/IntakeForm';
import { PHOTOS } from '@/lib/photos';

export const metadata: Metadata = {
  title: 'طرح مسئله / نیاز',
  description:
    'مسئله یا نیازتان را بنویسید؛ کسب‌وکار، سازمان، شهرداری یا پژوهشگر باشید. مسیر حل را پیشنهاد می‌دهیم. ثبت‌نام لازم نیست.',
};

/** `/intake` — نه یک صفحهٔ فرود برای هر خدمت؛ یک در ورودی برای هر مسئله (فایل مشخصات فاز ۰، بند ۲۰). */
export default function IntakePage() {
  return (
    <>
      <section className="relative isolate flex min-h-[280px] items-end overflow-hidden bg-[var(--neutral-900)] md:min-h-[340px]">
        <Image
          src={PHOTOS.solve.src}
          alt=""
          fill
          priority
          sizes="100vw"
          className="-z-20 object-cover"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 bg-gradient-to-t from-black/85 via-black/55 to-black/25"
        />
        <div className="page flex flex-col gap-3 pb-10 pt-20 text-white">
          <h1>
            <span className="block text-[30px] font-extrabold leading-[1.5] md:text-[42px]">
              مسئله یا نیاز خود را مطرح کنید
            </span>
          </h1>
          <p className="max-w-[56ch] text-[15px] leading-[2] text-white/85">
            نیازی به ثبت‌نام نیست. فقط همان چیزهایی را می‌پرسیم که برای شروع لازم است.
          </p>
        </div>
      </section>
      <div className="page mx-auto max-w-[820px] py-10">
        <IntakeForm />
      </div>
    </>
  );
}
