import type { Metadata } from 'next';

import { UserDetailView } from './UserDetailView';

export const metadata: Metadata = {
  title: 'جزئیات کاربر',
  description: 'نقش‌ها، وضعیت حساب، مشاهده به‌عنوان کاربر و تاریخچهٔ حسابرسی.',
};

/** `/admin/users/[id]` — FR-ADM-01، §6.5. */
export default async function AdminUserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <UserDetailView id={id} />;
}
