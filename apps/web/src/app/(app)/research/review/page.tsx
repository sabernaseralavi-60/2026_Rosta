import type { Metadata } from 'next';

import { ResearchReviewView } from './ResearchReviewView';

export const metadata: Metadata = {
  title: 'صف بررسی پژوهش',
  description: 'تحویل‌های مسیر پژوهش و مقاله‌های در انتظار راستی‌آزمایی.',
};

/** `/research/review` — منتور و استاد، FR-RES-01/02. */
export default function ResearchReviewPage() {
  return <ResearchReviewView />;
}
