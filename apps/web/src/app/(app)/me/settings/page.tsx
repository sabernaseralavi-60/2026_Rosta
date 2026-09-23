import type { Metadata } from 'next';

import { NotificationSettingsView } from './NotificationSettingsView';

export const metadata: Metadata = {
  title: 'تنظیمات اعلان',
  description: 'کدام خبرها به پیامک، ایمیل، تلگرام یا ایتا بیاید.',
};

/**
 * `/me/settings` — §3 «حریم خصوصی، اعلان‌ها، نشست‌های فعال».
 *
 * از M6 فقط بخش اعلان (FR-MSG-02، M6-09) را دارد؛ حریم خصوصی و نشست‌های
 * فعال با پنل حساب در M7 می‌آیند.
 */
export default function SettingsPage() {
  return <NotificationSettingsView />;
}
