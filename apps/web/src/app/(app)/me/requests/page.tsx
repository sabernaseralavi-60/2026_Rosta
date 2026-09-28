import type { Metadata } from 'next';

import { MyRequestsView } from './MyRequestsView';

export const metadata: Metadata = {
  title: 'درخواست‌های من',
  description: 'وضعیت مسئله‌ها و درخواست‌های همکاری که ثبت کرده‌ای، با پیام‌های تیم.',
};

/** `/me/requests` — داشبورد مشتری (ADR-0032). */
export default function MyRequestsPage() {
  return <MyRequestsView />;
}
