import type { Metadata } from 'next';

import { OpeningsView } from './OpeningsView';

export const metadata: Metadata = {
  title: 'آگهی‌های هم‌تیمی',
  description: 'تیم‌هایی که دنبال هم‌تیمی‌اند — نقش، مهارت لازم و تعهد زمانی.',
};

/** `/teams/openings` — §3.4، FR-TEAM-02. */
export default function OpeningsPage() {
  return <OpeningsView />;
}
