import type { Metadata } from 'next';

import { LibraryView } from './LibraryView';

export const metadata: Metadata = {
  title: 'کتابخانهٔ دروس',
  description: 'همهٔ دروس سامانه با کتاب‌ها، جزوه‌ها و محتوای هر کدام.',
};

/** `/library` — ویترین دروس و کتابخانه (ADR-0008). */
export default function LibraryPage() {
  return <LibraryView />;
}
