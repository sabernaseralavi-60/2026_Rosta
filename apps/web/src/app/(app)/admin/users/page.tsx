import type { Metadata } from 'next';

import { UsersView } from './UsersView';

export const metadata: Metadata = {
  title: 'کاربران و نقش‌ها',
  description: 'جستجو، فیلتر و مدیریت نقش و وضعیت حساب کاربران.',
};

/** `/admin/users` — FR-ADM-01. */
export default function AdminUsersPage() {
  return <UsersView />;
}
