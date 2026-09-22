import type { Metadata } from 'next';

import { PricingView } from './PricingView';

export const metadata: Metadata = {
  title: 'اشتراک',
  description: 'طرح‌های اشتراک کتابخانهٔ دروس و وضعیت اشتراک شما.',
};

/** `/pricing` — ADR-0009. */
export default function PricingPage() {
  return <PricingView />;
}
