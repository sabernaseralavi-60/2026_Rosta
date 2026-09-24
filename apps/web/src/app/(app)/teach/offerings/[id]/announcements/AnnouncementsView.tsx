'use client';

import { type FormEvent, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { Announcement } from '@/lib/api/courses';
import {
  deleteAnnouncement,
  PRIORITY_LABELS,
  publishAnnouncement,
  reviseAnnouncement,
  type TeachAnnouncement,
} from '@/lib/api/teach';
import { formatDateTime } from '@/lib/format/date';

/**
 * `/teach/offerings/[id]/announcements` — FR-EDU-06.
 *
 * «فوری» علاوه بر اعلان داخلی پیامک و پیام‌رسان هم می‌فرستد، پس انتخابش
 * یک تأیید دوم دارد: پیامک هزینه دارد و ساعت آرام را نمی‌شکند مگر همین.
 *
 * ویرایش و حذف (ADR-0021): نویسنده اعلان خودش را، استاد هر اعلان را.
 * ویرایش دوباره نمی‌فرستد ولی متن اعلان‌های رفته را بازنویسی می‌کند؛ حذف
 * آن‌ها را پس می‌گیرد. اهمیت پس از انتشار عوض نمی‌شود.
 */
export function AnnouncementsView() {
  const { offering, token, reload } = useOffering();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState<Announcement['priority']>('NORMAL');
  const [confirmUrgent, setConfirmUrgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const can = offering.permissions.publish_announcements;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (priority === 'URGENT' && !confirmUrgent) {
      setConfirmUrgent(true);
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await publishAnnouncement(
        offering.id,
        { title: title.trim(), body: body.trim(), priority },
        token,
      );
      setTitle('');
      setBody('');
      setPriority('NORMAL');
      setConfirmUrgent(false);
      setMessage('منتشر شد و به دانشجویان کلاس اعلان رفت.');
      await reload();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {can && (
        <Card className="flex flex-col gap-3">
          <h2 className="text-[18px]">اعلان تازه</h2>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <Input
              label="عنوان"
              value={title}
              required
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
            <Textarea
              label="متن"
              rows={4}
              value={body}
              required
              maxLength={4000}
              onChange={(event) => setBody(event.target.value)}
            />
            <div className="max-w-xs">
              <Field label="اهمیت">
                <select
                  className={SELECT_CLASS}
                  value={priority}
                  onChange={(event) => {
                    setPriority(event.target.value as Announcement['priority']);
                    setConfirmUrgent(false);
                  }}
                >
                  {(Object.keys(PRIORITY_LABELS) as Announcement['priority'][]).map((key) => (
                    <option key={key} value={key}>
                      {PRIORITY_LABELS[key]}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {confirmUrgent && (
              <p role="alert" className="text-[13.5px] text-[var(--fg-warning)]">
                اعلان فوری برای همهٔ دانشجویان کلاس پیامک هم می‌فرستد. برای ارسال دوباره دکمه را
                بزن.
              </p>
            )}
            {message && (
              <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
                {message}
              </p>
            )}
            {error && <ErrorLine>{error}</ErrorLine>}
            <div>
              <Button
                type="submit"
                variant={confirmUrgent ? 'danger' : 'primary'}
                loading={busy}
                disabled={!title.trim() || !body.trim()}
              >
                {confirmUrgent ? 'بله، با پیامک منتشر کن' : 'انتشار اعلان'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <section className="flex flex-col gap-3">
        <SectionHeader title="اعلان‌های منتشرشده" description="اعلان منقضی‌شده اینجا نمی‌آید." />
        {offering.announcements.length === 0 ? (
          <p className="text-[14px] text-[var(--fg-secondary)]">هنوز اعلانی منتشر نشده.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {offering.announcements.map((item) => (
              <li key={item.id}>
                <AnnouncementItem
                  item={item}
                  offeringId={offering.id}
                  token={token}
                  onChanged={reload}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AnnouncementItem({
  item,
  offeringId,
  token,
  onChanged,
}: {
  item: TeachAnnouncement;
  offeringId: string;
  token: string;
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [body, setBody] = useState(item.body);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState<'save' | 'delete' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: 'save' | 'delete', action: () => Promise<unknown>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
      await onChanged();
      setEditing(false);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  if (editing) {
    return (
      <Card className="flex flex-col gap-3">
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void run('save', () =>
              reviseAnnouncement(
                offeringId,
                item.id,
                { title: title.trim(), body: body.trim() },
                token,
              ),
            );
          }}
        >
          <Input
            label="عنوان"
            value={title}
            required
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
          />
          <Textarea
            label="متن"
            rows={4}
            value={body}
            required
            maxLength={4000}
            onChange={(event) => setBody(event.target.value)}
          />
          <p className="text-[13px] text-[var(--fg-secondary)]">
            دوباره فرستاده نمی‌شود؛ متن اعلانی که دانشجویان گرفته‌اند با همین عوض می‌شود و کنارش
            «ویرایش‌شده» می‌آید.
          </p>
          {error && <ErrorLine>{error}</ErrorLine>}
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              loading={busy === 'save'}
              disabled={!title.trim() || !body.trim()}
            >
              ذخیرهٔ ویرایش
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setTitle(item.title);
                setBody(item.body);
                setError(null);
              }}
            >
              انصراف
            </Button>
          </div>
        </form>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-1.5">
      <span className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{item.title}</span>
        {item.priority !== 'NORMAL' && (
          <Badge tone={item.priority === 'URGENT' ? 'danger' : 'warning'}>
            {item.priority === 'URGENT' ? 'فوری' : 'مهم'}
          </Badge>
        )}
      </span>
      <p className="whitespace-pre-line text-[14px]">{item.body}</p>
      <span className="text-[12px] text-[var(--fg-tertiary)]">
        {formatDateTime(item.published_at)}
        {item.edited_at && ` (ویرایش‌شده در ${formatDateTime(item.edited_at)})`}
      </span>
      {item.can_edit && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
            ویرایش
          </Button>
          <Button
            size="sm"
            variant={confirmDelete ? 'danger' : 'ghost'}
            loading={busy === 'delete'}
            onClick={() => {
              if (!confirmDelete) {
                setConfirmDelete(true);
                return;
              }
              void run('delete', () => deleteAnnouncement(offeringId, item.id, token));
            }}
          >
            {confirmDelete ? 'بله، حذف و پس گرفتن' : 'حذف'}
          </Button>
          {confirmDelete && (
            <span role="alert" className="text-[13px] text-[var(--fg-warning)]">
              اعلان از مرکز اعلان دانشجویان هم برداشته می‌شود؛ پیامک یا ایمیلی که رفته برنمی‌گردد.
            </span>
          )}
        </div>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}
