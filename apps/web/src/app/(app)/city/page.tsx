import type { Metadata } from 'next';

import { CityLabView } from './CityLabView';

export const metadata: Metadata = {
  title: 'آزمایشگاه شهر هوشمند',
  description: 'گردش‌کار هشت‌مرحله‌ای تولید خدمات ترافیکی برای شهرداری‌ها، و پروژه‌های شهری فعال.',
};

/** `/city` — FR-CITY-01، §7.9. */
export default function CityPage() {
  return <CityLabView />;
}
