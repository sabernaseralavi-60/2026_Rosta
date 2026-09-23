import type { Metadata } from 'next';

import { MyCertificatesView } from './MyCertificatesView';

export const metadata: Metadata = {
  title: 'گواهی‌های من',
  description: 'گواهی تکمیل پروژه، سطح پژوهش و درس — با پیوند راستی‌آزمایی برای رزومه.',
};

/** `/me/certificates` — §3.4، FR-PRJ-08. */
export default function MyCertificatesPage() {
  return <MyCertificatesView />;
}
