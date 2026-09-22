import type { Metadata } from 'next';

import { LeaderboardView } from './LeaderboardView';

export const metadata: Metadata = {
  title: 'رتبه‌بندی',
  description: 'ده نفر برتر نیم‌سال، بیشترین رشد ماه، و جایگاه خودت.',
};

/** `/leaderboard` — §3.4، FR-GAM-04. */
export default function LeaderboardPage() {
  return <LeaderboardView />;
}
