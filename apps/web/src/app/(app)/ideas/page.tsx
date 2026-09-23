import type { Metadata } from 'next';

import { IdeasView } from './IdeasView';

export const metadata: Metadata = {
  title: 'بانک ایده',
  description: 'ایده ثبت کن، رأی بده، و ایده‌های خوب را به پروژه یا کسب‌وکار تبدیل کن.',
};

/** `/ideas` — §3.4، FR-IDEA-01. */
export default function IdeasPage() {
  return <IdeasView />;
}
