import type { Metadata } from 'next';

import { WorkspaceView } from './WorkspaceView';

export const metadata: Metadata = {
  title: 'فضای کاری پروژه',
  description: 'مراحل، تیم، وظایف و گفتگوی پروژه.',
};

/** `/projects/[id]/workspace` — §3.4، FR-PRJ-05، FR-PRJ-06. */
export default async function WorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkspaceView id={id} />;
}
