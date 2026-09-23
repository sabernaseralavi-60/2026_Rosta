import Link from 'next/link';
import type { ReactNode } from 'react';

import { BadgeIcon } from '@/components/domain/BadgeTile';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import type { PublicProfile } from '@/lib/api/public';
import { formatDateLong, formatDateShort } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * بدنهٔ نیمرخ عمومی — FR-PROF-03. بی‌هوک، پس هم در صفحهٔ سرور `/u/…`
 * می‌نشیند و هم در پیش‌نمایش تنظیمات (کلاینت).
 *
 * بخش خاموش از سرور اصلاً نمی‌آید؛ اینجا فقط «خالی» می‌بیند و چیزی نشان
 * نمی‌دهد. موبایل، ایمیل، نمره و رتبهٔ کلاس فیلدی در پاسخ ندارند.
 */

export function PublicProfileBody({ profile }: { profile: PublicProfile }) {
  const academic = [profile.degree_level_fa, profile.field_of_study, profile.university]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1>
          <span className="block text-[30px]">{profile.name}</span>
        </h1>
        {academic && <p className="text-[15px] text-[var(--fg-secondary)]">{academic}</p>}
        {profile.bio && <p className="max-w-[65ch] text-[15px] leading-[1.9]">{profile.bio}</p>}
        <p className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--fg-tertiary)]">
          <span dir="ltr">@{profile.username}</span>
          <span>· عضو از {formatDateLong(profile.member_since)}</span>
          {profile.points && (
            <Badge tone="brand">
              سطح {toPersianDigits(profile.points.level)} — {profile.points.title_fa} ·{' '}
              {toPersianDigits(profile.points.total)} امتیاز
            </Badge>
          )}
        </p>
      </header>

      {profile.skills.length > 0 && (
        <Section title="مهارت‌های برتر">
          <ul className="flex flex-wrap gap-2">
            {profile.skills.map((skill) => (
              <li key={skill.title_fa}>
                <Badge tone={skill.verified ? 'success' : 'neutral'}>
                  {skill.title_fa} — سطح {toPersianDigits(skill.level)} از ۵
                  {skill.verified ? ' ✓ تأییدشده' : ''}
                </Badge>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.projects.length > 0 && (
        <Section title="پروژه‌های تکمیل‌شده">
          <ul className="grid gap-3 md:grid-cols-2">
            {profile.projects.map((project) => (
              <li key={project.id}>
                <Card className="flex h-full flex-col gap-1 p-4">
                  <span className="font-semibold">{project.title_fa}</span>
                  <span className="text-[13px] text-[var(--fg-secondary)]">
                    {project.kind_fa} · {project.role_fa}
                    {project.completed_at && ` · ${formatDateShort(project.completed_at)}`}
                  </span>
                </Card>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.certificates.length > 0 && (
        <Section title="گواهی‌ها">
          <ul className="flex flex-col gap-2">
            {profile.certificates.map((certificate) => (
              <li
                key={certificate.public_code}
                className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3"
              >
                <span className="text-[14px]">{certificate.title_fa}</span>
                <Link
                  href={`/verify/${certificate.public_code}`}
                  className="text-[13px] font-medium text-[var(--brand-700)]"
                >
                  راستی‌آزمایی <span dir="ltr">{certificate.public_code}</span> ←
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(profile.research_level || profile.research_outputs.length > 0) && (
        <Section title="پژوهش">
          {profile.research_level && (
            <p className="text-[14px]">
              سطح {toPersianDigits(profile.research_level)} از ۴ مسیر پژوهش تأیید شده —{' '}
              {profile.research_level_fa}
            </p>
          )}
          {profile.research_outputs.length > 0 && (
            <ul className="flex flex-col gap-2">
              {profile.research_outputs.map((output) => (
                <li key={output.title} className="text-[14px]">
                  <span className="font-medium" dir="auto">
                    {output.url ? (
                      <a
                        href={output.url}
                        rel="noopener noreferrer"
                        target="_blank"
                        className="hover:underline"
                      >
                        {output.title}
                      </a>
                    ) : (
                      output.title
                    )}
                  </span>
                  <span className="text-[13px] text-[var(--fg-secondary)]">
                    {' '}
                    — {output.kind_fa}
                    {output.venue && `، ${output.venue}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {profile.badges.length > 0 && (
        <Section title="نشان‌ها">
          <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {profile.badges.map((badge) => (
              <li key={badge.code}>
                <Card className="flex h-full flex-col items-center gap-1 p-4 text-center">
                  <BadgeIcon
                    icon={badge.icon}
                    earned
                    tier={badge.tier as 'BRONZE' | 'SILVER' | 'GOLD' | 'PLATINUM'}
                  />
                  <span className="text-[14px] font-semibold">{badge.title_fa}</span>
                  <span className="text-[12px] text-[var(--fg-tertiary)]">{badge.description}</span>
                </Card>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.skills.length === 0 &&
        profile.projects.length === 0 &&
        profile.certificates.length === 0 &&
        profile.badges.length === 0 &&
        !profile.research_level && (
          <p className="text-[14px] text-[var(--fg-secondary)]">
            هنوز دستاوردی برای نمایش نیست — پروژهٔ اول که تکمیل شود، اینجا می‌آید.
          </p>
        )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[18px]">{title}</h2>
      {children}
    </section>
  );
}
