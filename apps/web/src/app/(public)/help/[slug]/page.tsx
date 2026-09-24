import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { GUIDES, guideBySlug, readGuide, resolveGuideLink } from '@/lib/help/docs';
import { render } from '@/lib/markdown/render';

export const dynamicParams = false;

export function generateStaticParams() {
  return GUIDES.map((guide) => ({ slug: guide.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const guide = guideBySlug((await params).slug);
  return guide ? { title: guide.title, description: guide.summary } : {};
}

/** `/help/[slug]` — یک راهنما از `docs/user`، ساخته‌شده در زمان build (M7-19). */
export default async function HelpGuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const guide = guideBySlug((await params).slug);
  if (!guide) notFound();

  return (
    <div className="page py-10">
      <nav aria-label="مسیر" className="mx-auto mb-6 max-w-[var(--prose-max)] text-[13.5px]">
        <Link href="/help" className="font-medium text-[var(--fg-brand)] hover:underline">
          همهٔ راهنماها
        </Link>
      </nav>
      <article className="mx-auto flex max-w-[var(--prose-max)] flex-col gap-4 text-[15.5px]">
        {render(readGuide(guide.file), resolveGuideLink)}
      </article>
    </div>
  );
}
