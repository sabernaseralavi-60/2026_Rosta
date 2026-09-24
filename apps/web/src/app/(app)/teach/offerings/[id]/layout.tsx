import type { ReactNode } from 'react';

import { OfferingFrame } from '@/components/teach/OfferingFrame';

/** یک ارائه: سرصفحه و زبانه‌ها، و ارائه یک بار برای همهٔ زبانه‌ها. */
export default async function OfferingLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OfferingFrame offeringId={id}>{children}</OfferingFrame>;
}
