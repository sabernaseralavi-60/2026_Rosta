import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { PublicProfileBody } from '@/components/public/PublicProfileBody';
import { type PublicProfile, serverGet } from '@/lib/api/public';

/**
 * `/u/[username]` — نیمرخ عمومی (FR-PROF-03)، SSR.
 *
 * بی‌ورود و از سمت سرور، پس صاحب نیمرخ خصوصی هم اینجا ۴۰۴ می‌بیند؛ پیش‌نمایش
 * او در `/me/public-profile` است. یک دقیقه کش — خاموش کردن یک بخش باید زود
 * دیده شود.
 */

const REVALIDATE = 60;

async function load(username: string) {
  const result = await serverGet<PublicProfile>(
    `/profiles/${encodeURIComponent(username)}`,
    REVALIDATE,
  );
  return result.ok ? result.data : null;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ username: string }>;
}): Promise<Metadata> {
  const { username } = await params;
  const profile = await load(decodeURIComponent(username));
  if (!profile) return { title: 'نیمرخ پیدا نشد', robots: { index: false } };
  return {
    title: profile.name,
    description: `نیمرخ عمومی ${profile.name} در سیلپ — پروژه‌ها، گواهی‌ها و مهارت‌ها.`,
  };
}

export default async function PublicProfilePage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;
  const profile = await load(decodeURIComponent(username));
  if (!profile) notFound();
  return (
    <div className="page">
      <div className="mx-auto max-w-[960px] py-10">
        <PublicProfileBody profile={profile} />
      </div>
    </div>
  );
}
