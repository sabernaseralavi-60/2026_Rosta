import type { Metadata } from 'next';

import { LevelView } from './LevelView';

export const metadata: Metadata = {
  title: 'سطح پژوهش',
  description: 'راهنمای گام‌به‌گام، الگو و تحویل یک سطح از مسیر پژوهش.',
};

/** `/research/level/[n]` — §3.4، FR-RES-01. */
export default async function LevelPage({ params }: { params: Promise<{ n: string }> }) {
  const { n } = await params;
  return <LevelView level={Number(n)} />;
}
