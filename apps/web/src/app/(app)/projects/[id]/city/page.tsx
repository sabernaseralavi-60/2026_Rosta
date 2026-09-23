import type { Metadata } from 'next';

import { CityBoardView } from './CityBoardView';

export const metadata: Metadata = {
  title: 'گردش‌کار شهر هوشمند',
  description: 'هشت مرحلهٔ ثابت پروژهٔ شهری — از انتخاب محدوده تا داشبورد شهرداری.',
};

/** `/projects/[id]/city` — FR-CITY-01، §7.9. */
export default async function CityBoardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CityBoardView id={id} />;
}
