'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { readSession, type StoredSession } from './session';

/**
 * نشست جاری در سمت کلاینت.
 *
 * تا وقتی `loading` است هیچ تصمیمی گرفته نمی‌شود: در اولین رندر سرور،
 * `sessionStorage` وجود ندارد و خواندن زودهنگام، کاربر واردشده را به
 * صفحهٔ ورود می‌فرستد.
 */
export function useSession(options: { required?: boolean } = {}) {
  const { required = true } = options;
  const router = useRouter();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = readSession();
    setSession(stored);
    setLoading(false);
    if (required && !stored) {
      router.replace('/login');
    }
  }, [required, router]);

  return { session, accessToken: session?.accessToken ?? null, loading };
}
