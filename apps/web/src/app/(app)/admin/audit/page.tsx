import type { Metadata } from 'next';

import { AuditView } from './AuditView';

export const metadata: Metadata = {
  title: 'لاگ حسابرسی',
  description: 'هر عمل حساس: کیست، چه کرد، روی چه چیزی، کی و از کجا — فقط افزودنی.',
};

/** `/admin/audit` — FR-ADM-02. */
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ user_id?: string; action?: string }>;
}) {
  const { user_id: userId, action } = await searchParams;
  return <AuditView initialUserId={userId ?? ''} initialAction={action ?? ''} />;
}
