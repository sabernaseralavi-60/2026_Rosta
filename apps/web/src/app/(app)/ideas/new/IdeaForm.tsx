'use client';

import { useRouter } from 'next/navigation';
import { type FormEvent, useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type IdeaCategory,
  type IdeaCategoryOption,
  createIdea,
  fetchIdeaCategories,
} from '@/lib/api/ideas';
import { useSession } from '@/lib/auth/use-session';

/**
 * `/ideas/new` — FR-IDEA-01.
 *
 * «مسئله‌ای که حل می‌کند» جدا از شرح پرسیده می‌شود: ایده‌ای که مسئله‌اش
 * روشن نیست، نه رأی جمع می‌کند و نه به پروژه تبدیل می‌شود. پنج فیلد،
 * زیر سقف هفت فیلد §3.3.
 */
export function IdeaForm() {
  const router = useRouter();
  const { accessToken } = useSession();
  const [categories, setCategories] = useState<IdeaCategoryOption[]>([]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [problem, setProblem] = useState('');
  const [category, setCategory] = useState<IdeaCategory | ''>('');
  const [tags, setTags] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchIdeaCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const idea = await createIdea(accessToken, {
        title: title.trim(),
        body: body.trim(),
        problem: problem.trim() || null,
        category: category || null,
        tags: tags
          .split(/[,،]/)
          .map((tag) => tag.trim())
          .filter(Boolean),
        is_anonymous: anonymous,
      });
      router.push(`/ideas/${idea.id}`);
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof NetworkError
          ? cause.message
          : 'ایده ثبت نشد. دوباره تلاش کن.',
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto flex max-w-2xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>ثبت ایده</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          ایدهٔ خوب لازم نیست کامل باشد؛ فقط باید مسئله‌ای واقعی را نشانه بگیرد.
        </p>
      </header>

      <Input
        label="عنوان"
        required
        minLength={3}
        maxLength={120}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <Textarea
        label="مسئله‌ای که حل می‌کند"
        hint="چه کسی، کجا، با چه دردسری روبه‌روست؟"
        maxLength={1000}
        rows={3}
        value={problem}
        onChange={(event) => setProblem(event.target.value)}
      />
      <Textarea
        label="شرح ایده"
        required
        minLength={10}
        maxLength={4000}
        rows={6}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">دسته</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as IdeaCategory | '')}
            className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
          >
            <option value="">انتخاب نشده</option>
            {categories.map((option) => (
              <option key={option.code} value={option.code}>
                {option.title_fa}
              </option>
            ))}
          </select>
        </label>
        <Input
          label="برچسب‌ها"
          hint="با ویرگول جدا کن — حداکثر ۸"
          value={tags}
          onChange={(event) => setTags(event.target.value)}
        />
      </div>

      <label className="flex items-start gap-3 text-[14px] leading-[1.9]">
        <input
          type="checkbox"
          checked={anonymous}
          onChange={(event) => setAnonymous(event.target.checked)}
          className="mt-1.5 size-4 accent-[var(--brand-600)]"
        />
        <span>
          ناشناس ثبت کن
          <span className="block text-[12.5px] text-[var(--fg-tertiary)]">
            نامت به دیگران نشان داده نمی‌شود، ولی امتیاز ایده به خودت می‌رسد. ایدهٔ ناشناس به
            کسب‌وکار ارتقا نمی‌یابد، چون صفحهٔ کسب‌وکار بنیان‌گذار را نشان می‌دهد.
          </span>
        </span>
      </label>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <Button type="submit" loading={busy} disabled={!accessToken}>
          ثبت ایده
        </Button>
        <Button type="button" variant="ghost" onClick={() => router.back()}>
          انصراف
        </Button>
      </div>
    </form>
  );
}
