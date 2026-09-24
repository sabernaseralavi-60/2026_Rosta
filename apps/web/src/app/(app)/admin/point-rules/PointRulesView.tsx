'use client';

import { type FormEvent, useEffect, useMemo, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  fetchPointRules,
  type PointRule,
  type PointRuleUpdate,
  recalculatePoints,
  updatePointRule,
} from '@/lib/api/admin';
import { CATEGORY_LABELS } from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin/point-rules` — FR-GAM-02 و §9.9.
 *
 * «تغییر قاعده **گذشته‌نگر نیست**.» ویرایش فقط از این به بعد اثر دارد؛
 * برای اعمال به گذشته «بازمحاسبه» جداست و هیچ ردیفی را پاک نمی‌کند —
 * معکوس و ثبت دوباره. هر دو در لاگ حسابرسی می‌نشینند.
 */
export function PointRulesView() {
  const { accessToken } = useSession();
  const [rules, setRules] = useState<PointRule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchPointRules(accessToken)
      .then(setRules)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  const grouped = useMemo(() => {
    const groups = new Map<string, PointRule[]>();
    for (const rule of rules ?? []) {
      groups.set(rule.category, [...(groups.get(rule.category) ?? []), rule]);
    }
    return groups;
  }, [rules]);

  if (error && !rules) return <ErrorLine>{error}</ErrorLine>;
  if (!rules || !accessToken) return <SkeletonRow label="در حال بارگذاری قواعد" />;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>قواعد امتیاز</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          ویرایش فقط از این لحظه به بعد اثر دارد. برای اعمال به گذشته، بازمحاسبه را اجرا کن —
          ردیف‌های قبلی معکوس و دوباره ثبت می‌شوند و هیچ‌کدام پاک نمی‌شود.
        </p>
      </header>

      <RecalculateCard rules={rules} token={accessToken} />

      {[...grouped.entries()].map(([category, items]) => (
        <section key={category} aria-labelledby={`cat-${category}`} className="flex flex-col gap-2">
          <h2 id={`cat-${category}`} className="text-[18px]">
            {CATEGORY_LABELS[category as PointRule['category']] ?? category}
          </h2>
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {items.map((rule) => (
              <li key={rule.code} className="px-4 py-3">
                {editing === rule.code ? (
                  <RuleEditor
                    rule={rule}
                    token={accessToken}
                    onDone={(updated) => {
                      if (updated) {
                        setRules((current) =>
                          (current ?? []).map((r) => (r.code === updated.code ? updated : r)),
                        );
                      }
                      setEditing(null);
                    }}
                  />
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-col">
                      <span className="font-medium">
                        {rule.title_fa} {!rule.is_active && <Badge tone="neutral">غیرفعال</Badge>}
                      </span>
                      <span className="font-mono text-[12px] text-[var(--fg-tertiary)]" dir="ltr">
                        {rule.code}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-[13px] text-[var(--fg-secondary)]">
                      <span>
                        <strong className="text-[16px] text-[var(--fg-primary)]">
                          {toPersianDigits(Number(rule.base_points))}
                        </strong>{' '}
                        امتیاز
                      </span>
                      <span>{capsText(rule)}</span>
                      <Button variant="ghost" size="sm" onClick={() => setEditing(rule.code)}>
                        ویرایش
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function capsText(rule: PointRule): string {
  const caps = [
    rule.daily_cap && `روزانه ${toPersianDigits(rule.daily_cap)}`,
    rule.weekly_cap && `هفتگی ${toPersianDigits(rule.weekly_cap)}`,
    rule.term_cap && `نیم‌سال ${toPersianDigits(rule.term_cap)}`,
  ].filter(Boolean);
  return caps.length ? `سقف: ${caps.join('، ')}` : 'بی‌سقف';
}

type CapKey = 'daily_cap' | 'weekly_cap' | 'term_cap';
const CAPS: { key: CapKey; label: string }[] = [
  { key: 'daily_cap', label: 'سقف روزانه' },
  { key: 'weekly_cap', label: 'سقف هفتگی' },
  { key: 'term_cap', label: 'سقف نیم‌سال' },
];

function RuleEditor({
  rule,
  token,
  onDone,
}: {
  rule: PointRule;
  token: string;
  onDone: (updated: PointRule | null) => void;
}) {
  const [title, setTitle] = useState(rule.title_fa);
  const [base, setBase] = useState(String(Number(rule.base_points)));
  const [caps, setCaps] = useState<Record<CapKey, string>>({
    daily_cap: rule.daily_cap ? String(rule.daily_cap) : '',
    weekly_cap: rule.weekly_cap ? String(rule.weekly_cap) : '',
    term_cap: rule.term_cap ? String(rule.term_cap) : '',
  });
  const [active, setActive] = useState(rule.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    const patch: PointRuleUpdate = {
      title_fa: title.trim(),
      base_points: Number(base),
      is_active: active,
    };
    const clear: CapKey[] = [];
    for (const { key } of CAPS) {
      if (caps[key].trim()) patch[key] = Number(caps[key]);
      else if (rule[key] !== null) clear.push(key);
    }
    if (clear.length) patch.clear_caps = clear;
    setBusy(true);
    setError(null);
    try {
      onDone(await updatePointRule(token, rule.code, patch));
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
        <Input label="عنوان" value={title} onChange={(event) => setTitle(event.target.value)} />
        <Input
          label="امتیاز پایه"
          type="number"
          min={0}
          step="0.5"
          forceLtr
          value={base}
          onChange={(event) => setBase(event.target.value)}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {CAPS.map(({ key, label }) => (
          <Input
            key={key}
            label={label}
            hint="خالی یعنی بی‌سقف"
            type="number"
            min={1}
            forceLtr
            value={caps[key]}
            onChange={(event) => setCaps((current) => ({ ...current, [key]: event.target.value }))}
          />
        ))}
      </div>
      <label className="flex items-center gap-2 text-[14px]">
        <input
          type="checkbox"
          checked={active}
          onChange={(event) => setActive(event.target.checked)}
        />
        فعال
      </label>
      {error && <ErrorLine>{error}</ErrorLine>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={busy}>
          ذخیره (از این به بعد)
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => onDone(null)}>
          انصراف
        </Button>
      </div>
    </form>
  );
}

function RecalculateCard({ rules, token }: { rules: PointRule[]; token: string }) {
  const [code, setCode] = useState('');
  const [since, setSince] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!code) return;
    const rule = rules.find((r) => r.code === code);
    if (
      !window.confirm(
        `همهٔ ردیف‌های «${rule?.title_fa ?? code}» با قاعدهٔ فعلی بازمحاسبه شوند؟ ردیف‌ها پاک نمی‌شوند؛ معکوس و دوباره ثبت می‌شوند.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const outcome = await recalculatePoints(token, {
        rule_code: code,
        since: since ? new Date(since).toISOString() : undefined,
      });
      setResult(
        `${toPersianDigits(outcome.reversed)} ردیف معکوس و ${toPersianDigits(outcome.reawarded)} ردیف دوباره ثبت شد — ${toPersianDigits(outcome.users)} کاربر.`,
      );
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle as="h2" className="text-[16px]">
        بازمحاسبهٔ گذشته‌نگر
      </CardTitle>
      <form onSubmit={run} className="grid gap-3 md:grid-cols-[2fr_1fr_auto] md:items-end">
        <Field label="قاعده">
          <select
            className={SELECT_CLASS}
            value={code}
            onChange={(event) => setCode(event.target.value)}
          >
            <option value="">انتخاب کن…</option>
            {rules.map((rule) => (
              <option key={rule.code} value={rule.code}>
                {rule.title_fa}
              </option>
            ))}
          </select>
        </Field>
        <Input
          label="از تاریخ (اختیاری)"
          type="date"
          forceLtr
          value={since}
          onChange={(event) => setSince(event.target.value)}
        />
        <Button type="submit" variant="secondary" loading={busy} disabled={!code}>
          بازمحاسبه
        </Button>
      </form>
      {result && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {result}
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}
