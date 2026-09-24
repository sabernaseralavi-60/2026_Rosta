import type { Metadata } from 'next';

import { QuizEditorView } from './QuizEditorView';

export const metadata: Metadata = {
  title: 'ویرایشگر آزمون',
  description: 'سؤال‌ها، تنظیمات و انتشار آزمون.',
};

/** `/teach/quizzes/[id]/edit` — FR-QUIZ-01، M4-02. */
export default function QuizEditorPage() {
  return <QuizEditorView />;
}
