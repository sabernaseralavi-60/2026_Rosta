import type { ReactNode } from 'react';

import { AdminShell } from '@/components/admin/AdminShell';

/** ناحیهٔ مدیریت — §3.6. زیر پوستهٔ اپلیکیشن، با ناوبری فرعی خودش. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
