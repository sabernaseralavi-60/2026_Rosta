import type { Metadata } from 'next';

import { InboxView } from './InboxView';

export const metadata: Metadata = {
  title: 'پیام‌ها',
  description: 'گفت‌وگو با استاد و کانال درس‌هایت.',
};

/** `/messages` — صندوق گفت‌وگوها (ADR-0036). */
export default function MessagesPage() {
  return <InboxView />;
}
