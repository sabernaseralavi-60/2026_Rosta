import type { Metadata } from 'next';

import { QuestionBankView } from './QuestionBankView';

export const metadata: Metadata = {
  title: 'بانک سؤال',
  description: 'سؤال‌هایی که در آزمون‌های بعدی به کار می‌آیند.',
};

/** `/teach/question-bank` — M4-03. */
export default function QuestionBankPage() {
  return <QuestionBankView />;
}
