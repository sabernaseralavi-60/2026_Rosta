'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { ChatThread } from '@/components/messaging/ChatThread';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { type Conversation, fetchInbox } from '@/lib/api/messaging';
import { useSession } from '@/lib/auth/use-session';

/** سرتیتر از صندوق می‌آید (عنوان، درس، اجازهٔ نوشتن)؛ گفت‌وگوی غیرعضو ۴۰۴ می‌شود. */
export function ConversationView({ conversationId }: { conversationId: string }) {
  const { session, accessToken } = useSession();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    fetchInbox(accessToken)
      .then((rows) => {
        const found = rows.find((row) => row.id === conversationId);
        if (found) setConversation(found);
        else setMissing(true);
      })
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, conversationId]);

  const staff = session?.user.roles.some((role) =>
    ['INSTRUCTOR', 'TA', 'ADMIN', 'COORDINATOR'].includes(role),
  );

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label="مسیر" className="text-[13.5px]">
        <Link href="/messages" className="text-[var(--fg-brand)]">
          ← همهٔ پیام‌ها
        </Link>
      </nav>
      {error && <ErrorLine>{error}</ErrorLine>}
      {missing && <ErrorLine>این گفت‌وگو پیدا نشد یا به شما تعلق ندارد.</ErrorLine>}
      {!conversation && !error && !missing && <SkeletonCard label="در حال بارگذاری گفت‌وگو" />}
      {conversation && accessToken && (
        <>
          <header className="flex flex-col gap-1">
            <h1>{conversation.title}</h1>
            <p className="text-[14px] text-[var(--fg-secondary)]">{conversation.course_title}</p>
          </header>
          <ChatThread
            conversationId={conversation.id}
            token={accessToken}
            canWrite={conversation.can_write}
            staff={Boolean(staff)}
          />
        </>
      )}
    </div>
  );
}
