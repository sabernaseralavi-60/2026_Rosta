import type { Metadata } from 'next';

import { OfferingLessonsView } from './OfferingLessonsView';

export const metadata: Metadata = {
  title: 'درس‌نامه و چالش روزانه',
  description: 'نوشتن درس‌نامه، ساخت چالش روزانه از بانک سؤال و مدیریت شایستگی‌ها.',
};

/** `/teach/offerings/[id]/lessons` — حلقهٔ یادگیری روزانه (ADR-0036). */
export default function OfferingLessonsPage() {
  return <OfferingLessonsView />;
}
