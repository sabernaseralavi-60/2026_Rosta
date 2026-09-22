import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';

export default function NotFound() {
  return (
    <main id="main" className="page flex min-h-dvh items-center justify-center py-16">
      <EmptyState
        title="این صفحه پیدا نشد"
        description="شاید نشانی را اشتباه وارد کرده‌ای، یا این صفحه جابه‌جا شده است."
        action={
          <Button asChild>
            <Link href="/dashboard">بازگشت به داشبورد</Link>
          </Button>
        }
      />
    </main>
  );
}
