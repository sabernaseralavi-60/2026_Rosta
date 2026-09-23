import type { Metadata } from 'next';

import { FindTeammatesView } from './FindTeammatesView';

export const metadata: Metadata = {
  title: 'جستجوی هم‌تیمی',
  description: 'هم‌تیمی‌ای پیدا کن که مهارتی دارد که تیمت ندارد.',
};

/** `/teams/find` — §3.4، FR-TEAM-01. */
export default function FindTeammatesPage() {
  return <FindTeammatesView />;
}
