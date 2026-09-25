import type { Metadata } from 'next';

import { QaView } from './QaView';

export const metadata: Metadata = {
  title: 'پرسش‌وپاسخ درس',
  description: 'پرسش‌های این درس و پاسخ همکلاسی‌ها و استاد.',
};

/** `/courses/[offeringId]/qa` — §3.4. `?thread=` از پیوند اعلان می‌آید. */
export default async function OfferingQaPage({
  params,
  searchParams,
}: {
  params: Promise<{ offeringId: string }>;
  searchParams: Promise<{ thread?: string }>;
}) {
  const [{ offeringId }, { thread }] = await Promise.all([params, searchParams]);
  return <QaView offeringId={offeringId} initialThreadId={thread ?? null} />;
}
