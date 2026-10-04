import type { Metadata } from 'next';

import { OfferingMessagesView } from './OfferingMessagesView';

export const metadata: Metadata = {
  title: 'پیام‌ها و گفت‌وگو با دانشجویان',
  description: 'ارسال پیام به همهٔ کلاس یا چند دانشجو، و گفت‌وگوی خصوصی با هر دانشجو.',
};

/** `/teach/offerings/[id]/messages` — جایگزین گروه تلگرام درس (ADR-0036). */
export default function OfferingMessagesPage() {
  return <OfferingMessagesView />;
}
