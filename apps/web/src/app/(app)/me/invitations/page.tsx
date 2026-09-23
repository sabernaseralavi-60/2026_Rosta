import type { Metadata } from 'next';

import { InvitationsView } from './InvitationsView';

export const metadata: Metadata = {
  title: 'دعوت‌های من',
  description: 'دعوت‌های باز برای پیوستن به تیم پروژه یا کسب‌وکار.',
};

/** `/me/invitations` — FR-TEAM-03. */
export default function InvitationsPage() {
  return <InvitationsView />;
}
