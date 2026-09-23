import type { Metadata } from 'next';

import { PointRulesView } from './PointRulesView';

export const metadata: Metadata = {
  title: 'قواعد امتیاز',
  description: 'امتیاز پایه، سقف‌ها و بازمحاسبهٔ گذشته‌نگر — هر تغییر در لاگ حسابرسی.',
};

/** `/admin/point-rules` — FR-GAM-02، §9.9. */
export default function PointRulesPage() {
  return <PointRulesView />;
}
