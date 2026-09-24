import type { ReactNode } from 'react';

import { TeachShell } from '@/components/teach/TeachShell';

/** ناحیهٔ استاد — §3.5. زیر پوستهٔ اپلیکیشن، با ناوبری فرعی خودش (ADR-0019). */
export default function TeachLayout({ children }: { children: ReactNode }) {
  return <TeachShell>{children}</TeachShell>;
}
