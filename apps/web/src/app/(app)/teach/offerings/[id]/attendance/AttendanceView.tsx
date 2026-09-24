'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { INPUT_CLASS, SectionHeader, todayInput } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  ATTENDANCE_LABELS,
  type AttendanceSession,
  type AttendanceStatus,
  fetchAttendanceSessions,
  fetchAttendanceSheet,
  fetchRoster,
  recordAttendance,
  type RosterEntry,
} from '@/lib/api/teach';
import { cn } from '@/lib/cn';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const STATUSES: AttendanceStatus[] = ['PRESENT', 'LATE', 'ABSENT', 'EXCUSED'];

const ACTIVE_CLASS: Record<AttendanceStatus, string> = {
  PRESENT:
    'bg-[color-mix(in_oklch,var(--success-500)_16%,transparent)] text-[var(--fg-success)] border-[var(--success-600)]',
  LATE: 'bg-[color-mix(in_oklch,var(--warning-500)_20%,transparent)] text-[var(--fg-warning)] border-[var(--warning-600)]',
  ABSENT:
    'bg-[color-mix(in_oklch,var(--danger-500)_14%,transparent)] text-[var(--fg-danger)] border-[var(--danger-600)]',
  EXCUSED:
    'bg-[color-mix(in_oklch,var(--info-500)_14%,transparent)] text-[var(--fg-info)] border-[var(--info-500)]',
};

/**
 * `/teach/offerings/[id]/attendance` — «ثبت سریع حضور و غیاب» (§3.5، FR-EDU-05).
 *
 * همه پیش‌فرض حاضرند؛ استاد فقط غایب‌ها را لمس می‌کند. یک درخواست برای
 * کل کلاس. روزی که قبلاً ثبت شده، با همان وضعیت‌ها باز می‌شود و ذخیرهٔ
 * دوباره اصلاح است، نه جلسهٔ دوم.
 */
export function AttendanceView() {
  const { offering, token } = useOffering();
  const [students, setStudents] = useState<RosterEntry[] | null>(null);
  const [sessions, setSessions] = useState<AttendanceSession[]>([]);
  const [heldOn, setHeldOn] = useState(todayInput());
  const [week, setWeek] = useState('');
  const [topic, setTopic] = useState('');
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [existing, setExisting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(() => {
    fetchAttendanceSessions(offering.id, token)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [offering.id, token]);

  useEffect(() => {
    fetchRoster(offering.id, token)
      .then((rows) =>
        setStudents(rows.filter((r) => r.status === 'ACTIVE' || r.status === 'COMPLETED')),
      )
      .catch((cause) => setError(errorText(cause)));
    loadSessions();
  }, [offering.id, token, loadSessions]);

  // روز انتخاب‌شده: اگر ثبت شده، همان را باز کن؛ وگرنه همه حاضر.
  useEffect(() => {
    if (!students || !heldOn) return;
    let cancelled = false;
    setMessage(null);
    fetchAttendanceSheet(offering.id, heldOn, token)
      .then((sheet) => {
        if (cancelled) return;
        const byStudent = Object.fromEntries(sheet.marks.map((m) => [m.student_id, m]));
        setMarks(
          Object.fromEntries(
            students.map((s) => [s.student_id, byStudent[s.student_id]?.status ?? 'PRESENT']),
          ),
        );
        setNotes(
          Object.fromEntries(
            sheet.marks.filter((m) => m.note).map((m) => [m.student_id, m.note ?? '']),
          ),
        );
        setWeek(sheet.week_number ? String(sheet.week_number) : '');
        setTopic(sheet.topic ?? '');
        setExisting(true);
      })
      .catch((cause) => {
        if (cancelled) return;
        if (!(cause instanceof ApiError && cause.status === 404)) setError(errorText(cause));
        setMarks(Object.fromEntries(students.map((s) => [s.student_id, 'PRESENT'])));
        setNotes({});
        setTopic('');
        setExisting(false);
      });
    return () => {
      cancelled = true;
    };
  }, [students, heldOn, offering.id, token]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!students) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const { recorded } = await recordAttendance(
        offering.id,
        {
          held_on: heldOn,
          week_number: week ? Number(week) : null,
          topic: topic.trim() || null,
          entries: students.map((s) => ({
            student_id: s.student_id,
            status: marks[s.student_id] ?? 'PRESENT',
            note: notes[s.student_id]?.trim() || null,
          })),
        },
        token,
      );
      setMessage(
        `${existing ? 'اصلاح' : 'ثبت'} شد — ${toPersianDigits(recorded)} دانشجو، ${formatDateLong(heldOn)}.`,
      );
      setExisting(true);
      loadSessions();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  if (!students && !error) return <SkeletonRow label="در حال بارگذاری فهرست کلاس" />;
  if (!students) return <ErrorLine>{error}</ErrorLine>;

  const counts = STATUSES.map(
    (status) => [status, students.filter((s) => marks[s.student_id] === status).length] as const,
  );

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={save} className="flex flex-col gap-4">
        <SectionHeader
          title={existing ? 'اصلاح حضور این روز' : 'ثبت حضور'}
          description="همه حاضر فرض شده‌اند؛ فقط وضعیت غایب‌ها و تأخیری‌ها را عوض کن."
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="تاریخ جلسه">
            <input
              type="date"
              className={INPUT_CLASS}
              value={heldOn}
              required
              max={todayInput()}
              onChange={(event) => setHeldOn(event.target.value)}
            />
            <span className="text-[12px] font-normal text-[var(--fg-tertiary)]">
              {heldOn ? formatDateLong(heldOn) : ''}
            </span>
          </Field>
          <Field label="هفته">
            <select className={SELECT_CLASS} value={week} onChange={(e) => setWeek(e.target.value)}>
              <option value="">—</option>
              {Array.from({ length: 17 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  هفتهٔ {toPersianDigits(n)}
                </option>
              ))}
            </select>
          </Field>
          <Input
            label="موضوع جلسه (اختیاری)"
            value={topic}
            maxLength={200}
            onChange={(event) => setTopic(event.target.value)}
          />
        </div>

        {students.length === 0 ? (
          <EmptyState
            title="دانشجوی فعالی در کلاس نیست"
            description="حضور فقط برای دانشجوی ثبت‌نام‌شدهٔ فعال ثبت می‌شود."
          />
        ) : (
          <Card className="flex flex-col gap-0 p-0">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-4 py-3 text-[13px]">
              <span className="flex flex-wrap gap-3" aria-live="polite">
                {counts.map(([status, count]) => (
                  <span key={status}>
                    {ATTENDANCE_LABELS[status]}: <strong>{toPersianDigits(count)}</strong>
                  </span>
                ))}
              </span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  setMarks(Object.fromEntries(students.map((s) => [s.student_id, 'PRESENT'])))
                }
              >
                همه حاضر
              </Button>
            </div>
            <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
              {students.map((student) => {
                const current = marks[student.student_id] ?? 'PRESENT';
                const name = student.student_name ?? 'بی‌نام';
                return (
                  <li key={student.student_id} className="flex flex-col gap-2 px-4 py-3">
                    <fieldset className="flex flex-wrap items-center justify-between gap-2">
                      <legend className="float-start font-medium">{name}</legend>
                      <div className="flex gap-1">
                        {STATUSES.map((status) => (
                          <label
                            key={status}
                            className={cn(
                              'cursor-pointer rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13px] has-[:focus-visible]:outline has-[:focus-visible]:outline-2',
                              current === status
                                ? ACTIVE_CLASS[status]
                                : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
                            )}
                          >
                            <input
                              type="radio"
                              className="sr-only"
                              name={`mark-${student.student_id}`}
                              value={status}
                              checked={current === status}
                              onChange={() =>
                                setMarks((m) => ({ ...m, [student.student_id]: status }))
                              }
                            />
                            {ATTENDANCE_LABELS[status]}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    {current === 'EXCUSED' && (
                      <input
                        aria-label={`دلیل غیبت موجه ${name}`}
                        className={INPUT_CLASS}
                        placeholder="دلیل (مثلاً گواهی پزشکی)"
                        maxLength={500}
                        value={notes[student.student_id] ?? ''}
                        onChange={(event) =>
                          setNotes((n) => ({ ...n, [student.student_id]: event.target.value }))
                        }
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
        {message && (
          <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
            {message}
          </p>
        )}
        {error && <ErrorLine>{error}</ErrorLine>}
        {students.length > 0 && (
          <div>
            <Button type="submit" loading={busy} disabled={!heldOn}>
              {existing ? 'ذخیرهٔ اصلاح' : 'ثبت حضور کلاس'}
            </Button>
          </div>
        )}
      </form>

      <section className="flex flex-col gap-3">
        <SectionHeader title="جلسه‌های ثبت‌شده" />
        {sessions.length === 0 ? (
          <p className="text-[14px] text-[var(--fg-secondary)]">هنوز جلسه‌ای ثبت نشده.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {sessions.map((session) => (
              <li key={session.held_on}>
                <button
                  type="button"
                  onClick={() => setHeldOn(session.held_on)}
                  aria-current={session.held_on === heldOn ? 'true' : undefined}
                  className="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-start hover:bg-[var(--bg-sunken)] aria-[current=true]:bg-[var(--brand-50)]"
                >
                  <span className="flex flex-col">
                    <span className="font-medium">{formatDateLong(session.held_on)}</span>
                    <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                      {session.week_number ? `هفتهٔ ${toPersianDigits(session.week_number)}` : ''}
                      {session.topic ? ` · ${session.topic}` : ''}
                    </span>
                  </span>
                  <span className="text-[13px] text-[var(--fg-secondary)]">
                    حاضر {toPersianDigits(session.present)} · تأخیر {toPersianDigits(session.late)}{' '}
                    · غایب {toPersianDigits(session.absent)} · موجه{' '}
                    {toPersianDigits(session.excused)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
