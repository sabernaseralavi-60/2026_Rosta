import type { Metadata } from 'next';
import Image from 'next/image';

import { CollabForm } from '@/components/public/CollabForm';
import { COLLAB_WAYS } from '@/lib/api/intake';
import { PHOTOS } from '@/lib/photos';

export const metadata: Metadata = {
  title: 'همکاری با ما',
  description: 'متخصص، پژوهشگر یا فارغ‌التحصیل هستید؟ در پروژه‌ها و پژوهش‌های واقعی عضو تیم شوید.',
};

/** `/collaborate` — «۱۰ راهی که می‌توانید همکار ما شوید» و فرم چندگامی (فایل مشخصات فاز ۰، بند ۲۳). */
export default function CollaboratePage() {
  return (
    <>
      <section className="relative isolate flex min-h-[280px] items-end overflow-hidden bg-[var(--neutral-900)] md:min-h-[340px]">
        <Image
          src={PHOTOS.collab.src}
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
              🤝 همکاری با ما
            </span>
          </h1>
          <p className="max-w-[56ch] text-[15px] leading-[2] text-white/85">
            در پروژه‌ها و پژوهش‌های واقعی عضو تیم شوید؛ حتی پس از پایان تحصیل.
          </p>
        </div>
      </section>
      <div className="page mx-auto flex max-w-[820px] flex-col gap-8 py-10">
        <section aria-labelledby="ways-title">
          <h2 id="ways-title" className="mb-4 text-[20px]">
            ده راهی که می‌توانید همکار ما شوید
          </h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {COLLAB_WAYS.map((way) => (
              <li
                key={way}
                className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 text-[14px]"
              >
                <span aria-hidden="true" className="text-[var(--brand-600)]">
                  ◆
                </span>
                {way}
              </li>
            ))}
          </ul>
        </section>
        <CollabForm />
      </div>
    </>
  );
}
