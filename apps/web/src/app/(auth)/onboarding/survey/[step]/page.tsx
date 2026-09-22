import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { SurveySteps } from './SurveySteps';

export const metadata: Metadata = {
  title: 'ارزیابی نیمرخ',
  description: 'چهار گام کوتاه تا اولین پیشنهادهای پروژه.',
};

const TOTAL_STEPS = 4;

/**
 * `/onboarding/survey/[step]` — §3.3، FR-PROF-01.
 *
 * گام‌ها از پیش ساخته می‌شوند تا ناوبری بین آن‌ها فوری باشد؛ عدد نامعتبر
 * ۴۰۴ می‌گیرد، نه اینکه بی‌صدا به گام ۱ برگردد.
 */
export function generateStaticParams() {
  return Array.from({ length: TOTAL_STEPS }, (_, index) => ({ step: String(index + 1) }));
}

export default async function SurveyStepPage({
  params,
}: {
  params: Promise<{ step: string }>;
}) {
  const { step } = await params;
  const parsed = Number(step);

  if (!Number.isInteger(parsed) || parsed < 1 || parsed > TOTAL_STEPS) {
    notFound();
  }

  return <SurveySteps step={parsed} />;
}
