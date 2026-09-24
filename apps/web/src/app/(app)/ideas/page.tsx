import type { Metadata } from 'next';

import type { IdeaCategoryOption } from '@/lib/api/ideas';
import { serverGet } from '@/lib/api/public';

import { IdeasView } from './IdeasView';

export const metadata: Metadata = {
  title: 'بانک ایده',
  description: 'ایده ثبت کن، رأی بده، و ایده‌های خوب را به پروژه یا کسب‌وکار تبدیل کن.',
};

// هر درخواست رندر می‌شود تا ساختی که به API دسترسی نداشت، یک ساعت فهرست
// دستهٔ خالی را کش نکند؛ خود دسته‌ها یک ساعت در کش داده می‌مانند.
export const dynamic = 'force-dynamic';

/**
 * `/ideas` — §3.4، FR-IDEA-01.
 *
 * دسته‌ها سمت سرور می‌آیند (M7-15): پیش از این، ردیف دسته‌ها پس از بارگذاری
 * فهرست ظاهر می‌شد و کارت‌ها را پایین می‌راند (CLS ۰٫۰۹).
 */
export default async function IdeasPage() {
  const categories = await serverGet<IdeaCategoryOption[]>('/ideas/categories', 3600);
  return <IdeasView initialCategories={categories.ok ? categories.data : []} />;
}
