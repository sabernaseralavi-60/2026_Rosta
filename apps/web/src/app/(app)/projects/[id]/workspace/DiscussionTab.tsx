'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Activity, type Message, deleteMessage, postMessage } from '@/lib/api/workspace';
import { formatRelative } from '@/lib/format/date';

/**
 * گفتگوی تیمی و جریان فعالیت — FR-PRJ-06.
 *
 * نخ یک‌سطحی است: پاسخ به پیام اصلی بله، پاسخ به پاسخ نه (§4.6). همین
 * محدودیت، گفتگو را خواندنی نگه می‌دارد و رابط را ساده.
 *
 * جریان فعالیت جدا از گفتگوست چون دو چیز متفاوت‌اند: یکی حرف آدم‌هاست و
 * دیگری کارنامهٔ سامانه. قاتی کردنشان هر دو را بی‌ارزش می‌کند.
 */

const MAX_BODY = 4000;

export function DiscussionTab({
  projectId,
  messages,
  currentUserId,
  isLead,
  accessToken,
  onChanged,
}: {
  projectId: string;
  messages: Message[];
  currentUserId: string | null;
  isLead: boolean;
  accessToken: string;
  onChanged: () => void;
}) {
  const [body, setBody] = useState('');
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roots = messages.filter((message) => message.parent_id === null);
  const repliesOf = (id: string) => messages.filter((message) => message.parent_id === id);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await postMessage(projectId, { body: body.trim(), parent_id: replyTo }, accessToken);
      setBody('');
      setReplyTo(null);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    try {
      await deleteMessage(projectId, id, accessToken);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-col gap-3">
        <form onSubmit={handleSend} className="flex flex-col gap-3">
          <Textarea
            label={replyTo ? 'پاسخ' : 'پیام تازه'}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            maxLength={MAX_BODY}
            rows={3}
            placeholder="چیزی بنویس که تیم لازم دارد بداند…"
          />
          {error && (
            <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
              {error}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" loading={busy} disabled={!body.trim()}>
              ارسال
            </Button>
            {replyTo && (
              <Button type="button" size="sm" variant="ghost" onClick={() => setReplyTo(null)}>
                لغو پاسخ
              </Button>
            )}
          </div>
        </form>
      </Card>

      {roots.length === 0 ? (
        <EmptyState
          title="هنوز گفتگویی شروع نشده"
          description="اولین پیام معمولاً سخت‌ترین است. بنویس تیم کجای کار است."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {roots.map((message) => (
            <li key={message.id}>
              <Card className="flex flex-col gap-2">
                <MessageBody
                  message={message}
                  canDelete={isLead || message.author_id === currentUserId}
                  onDelete={() => handleDelete(message.id)}
                  onReply={() => setReplyTo(message.id)}
                />

                {repliesOf(message.id).length > 0 && (
                  <ul className="mt-1 flex flex-col gap-2 border-s-2 border-[var(--border-subtle)] ps-3">
                    {repliesOf(message.id).map((reply) => (
                      <li key={reply.id}>
                        <MessageBody
                          message={reply}
                          canDelete={isLead || reply.author_id === currentUserId}
                          onDelete={() => handleDelete(reply.id)}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageBody({
  message,
  canDelete,
  onDelete,
  onReply,
}: {
  message: Message;
  canDelete: boolean;
  onDelete: () => void;
  onReply?: () => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">
          {message.author_name ?? 'عضو تیم'}
        </span>
        <span className="text-[12px] text-[var(--fg-tertiary)]">
          {formatRelative(message.created_at)}
        </span>
      </div>
      <p className="whitespace-pre-line text-[14px] leading-[1.95] text-[var(--fg-secondary)]">
        {message.body}
      </p>
      <div className="flex gap-1">
        {onReply && (
          <Button variant="ghost" size="sm" onClick={onReply}>
            پاسخ
          </Button>
        )}
        {canDelete && (
          <Button variant="ghost" size="sm" onClick={onDelete}>
            حذف
          </Button>
        )}
      </div>
    </div>
  );
}

export function ActivityTab({ activity }: { activity: Activity[] }) {
  if (activity.length === 0) {
    return (
      <EmptyState
        title="هنوز فعالیتی ثبت نشده"
        description="هر کاری که در پروژه انجام شود — پیوستن عضو، تحویل، بررسی — اینجا می‌آید."
      />
    );
  }

  return (
    <ol className="flex flex-col gap-3">
      {activity.map((item) => (
        <li
          key={item.id}
          className="flex flex-col gap-0.5 border-s-2 border-[var(--border-subtle)] ps-3"
        >
          <p className="text-[14px] text-[var(--fg-primary)]">{item.summary}</p>
          <p className="text-[12px] text-[var(--fg-tertiary)]">
            {item.actor_name ? `${item.actor_name} — ` : ''}
            {formatRelative(item.created_at)}
          </p>
        </li>
      ))}
    </ol>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
