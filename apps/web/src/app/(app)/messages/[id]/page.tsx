import type { Metadata } from 'next';

import { ConversationView } from './ConversationView';

export const metadata: Metadata = {
  title: 'گفت‌وگو',
  description: 'پیام‌های یک گفت‌وگو.',
};

/** `/messages/[id]` — یک گفت‌وگو (ADR-0036). */
export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConversationView conversationId={id} />;
}
