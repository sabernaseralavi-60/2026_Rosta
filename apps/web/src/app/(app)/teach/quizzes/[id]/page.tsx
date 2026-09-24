import { redirect } from 'next/navigation';

/** `/teach/quizzes/[id]` — صفحهٔ پیش‌فرض آزمون همان ویرایشگر است. */
export default async function QuizIndexPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/teach/quizzes/${id}/edit`);
}
