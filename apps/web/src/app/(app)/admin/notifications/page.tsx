import type { Metadata } from 'next';

import { MessagingAdminView } from './MessagingAdminView';

export const metadata: Metadata = {
  title: 'صف ارسال و الگوهای پیام',
  description: 'وضعیت پیامک، ایمیل و پیام‌رسان‌ها، تلاش دوباره، و ویرایش الگو با پیش‌نمایش.',
};

/** `/admin/notifications` — §7.10، FR-MSG-03. */
export default function MessagingAdminPage() {
  return <MessagingAdminView />;
}
