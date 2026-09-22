import Link from 'next/link';

import { MatchRing } from '@/components/domain/MatchRing';
import { ReasonList } from '@/components/domain/ReasonList';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import type { ProjectKind, ProjectSummary, Reason } from '@/lib/api/projects';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * کارت پروژه — PRD §10.6.
 *
 * «عنوان، خلاصه، نوع، دشواری، حلقهٔ درصد تطابق، مهارت‌های لازم.»
 *
 * کارت هم در فهرست عمومی (بدون تطابق) و هم در پیشنهادها (با تطابق و
 * دلیل) به کار می‌رود؛ `match` و `reasons` اختیاری‌اند.
 */

const KIND_TONE: Record<ProjectKind, BadgeTone> = {
  A_VENTURE: 'accent',
  B_RESEARCH: 'research',
  C_PROBLEM: 'brand',
  D_PERSONAL: 'neutral',
};

export interface ProjectCardProps {
  project: ProjectSummary;
  matchScore?: number;
  reasons?: Reason[];
  /** §8.11 — «چالش‌برانگیز، اگر آماده‌ای». */
  isStretch?: boolean;
  /** اقدام‌های زیر کارت، مثل دکمه‌های بازخورد پیشنهاد. */
  footer?: React.ReactNode;
  className?: string;
}

export function ProjectCard({
  project,
  matchScore,
  reasons,
  isStretch = false,
  footer,
  className,
}: ProjectCardProps) {
  return (
    <Card variant="interactive" className={cn('flex flex-col gap-4', className)}>
      <div className="flex items-start gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={KIND_TONE[project.kind]}>{project.kind_fa}</Badge>
            <Badge tone="neutral">دشواری: {project.difficulty_fa}</Badge>
            {isStretch && <Badge tone="warning">چالش‌برانگیز — اگر آماده‌ای</Badge>}
          </div>

          <h3 className="text-[17px] font-semibold text-[var(--fg-primary)]">
            {/* کل کارت با این پوشش قابل کلیک می‌شود، بدون تودرتو شدن لینک‌ها. */}
            <Link
              href={`/projects/${project.id}`}
              className="after:absolute after:inset-0 focus-visible:outline-none"
            >
              {project.title_fa}
            </Link>
          </h3>

          {project.summary && (
            <p className="line-clamp-2 text-[13.5px] leading-[1.9] text-[var(--fg-secondary)]">
              {project.summary}
            </p>
          )}
        </div>

        {matchScore !== undefined && <MatchRing score={matchScore} />}
      </div>

      {reasons && reasons.length > 0 && <ReasonList reasons={reasons} />}

      <dl className="flex flex-wrap gap-x-5 gap-y-1.5 text-[12.5px] text-[var(--fg-tertiary)]">
        {project.time_commitment_hpw !== null && (
          <Fact label="تعهد زمانی">
            {toPersianDigits(project.time_commitment_hpw)} ساعت در هفته
          </Fact>
        )}
        <Fact label="اندازهٔ تیم">
          {project.team_size_min === project.team_size_max
            ? `${toPersianDigits(project.team_size_min)} نفر`
            : `${toPersianDigits(project.team_size_min)} تا ${toPersianDigits(project.team_size_max)} نفر`}
        </Fact>
        {project.open_seats > 0 && (
          <Fact label="جای خالی">{toPersianDigits(project.open_seats)} نفر</Fact>
        )}
      </dl>

      {/* اقدام‌ها باید بالای پوشش لینک بنشینند تا کلیکشان به کارت نرود. */}
      {footer && <div className="relative z-10">{footer}</div>}
    </Card>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1">
      <dt className="text-[var(--fg-tertiary)]">{label}:</dt>
      <dd className="font-medium text-[var(--fg-secondary)]">{children}</dd>
    </div>
  );
}
