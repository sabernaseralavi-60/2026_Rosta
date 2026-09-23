import type { Metadata } from 'next';

import { PublicProfileSettingsView } from './PublicProfileSettingsView';

export const metadata: Metadata = {
  title: 'نیمرخ عمومی من',
  description: 'روشن و خاموش کردن نیمرخ عمومی و هر بخش آن، با پیش‌نمایش.',
};

/** `/me/public-profile` — FR-PROF-03 «هر بخش قابل روشن/خاموش کردن». */
export default function PublicProfileSettingsPage() {
  return <PublicProfileSettingsView />;
}
