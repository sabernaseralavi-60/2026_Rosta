import type { Metadata } from 'next';

import { SettingsView } from './SettingsView';

export const metadata: Metadata = {
  title: 'تنظیمات ارائه',
  description: 'وضعیت، ثبت‌نام، وزن نمره و کپی محتوا.',
};

/** `/teach/offerings/[id]/settings` — ADR-0019. */
export default function SettingsPage() {
  return <SettingsView />;
}
