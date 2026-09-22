import type { Metadata } from 'next';

import { BasicInfoForm } from './BasicInfoForm';

export const metadata: Metadata = {
  title: 'اطلاعات پایه',
  description: 'نام و اطلاعات دانشگاهی خود را وارد کنید.',
};

/** `/onboarding/basic` — §3.3. */
export default function BasicInfoPage() {
  return <BasicInfoForm />;
}
