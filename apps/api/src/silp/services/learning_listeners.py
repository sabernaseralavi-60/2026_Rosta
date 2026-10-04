"""شنوندهٔ چالش روزانه — ADR-0036 §۶.

وقتی تلاشِ یک **چالش** تصحیح می‌شود: شایستگی و استمرار به‌روز می‌شود و امتیاز (XP) ثبت
می‌شود. تصحیح دستی/اعتراض هم همین رویداد را می‌فرستد؛ `process_checkpoint_attempt` برای هر
تلاش فقط یک‌بار کار می‌کند، پس دوباره‌شماری نیست.

امتیازها فقط از قاعده‌های قابل‌ویرایش `point_rules` می‌آیند (نه ثابت کد) و همه سقف دارند.
چالش نمرهٔ رسمی نمی‌سازد: `reconcile_quiz` (امتیاز آزمون) برای نوع `CHECKPOINT` رد می‌شود.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from silp.models.quiz import Quiz, QuizAttempt
from silp.services import events
from silp.services.learning_service import HIGH_SCORE, LearningService
from silp.services.points_service import Award, PointsService

# شناسهٔ ثابت برای تولید source_id قطعی نقطهٔ عطف استمرار (uuid5).
_STREAK_NS = uuid.UUID("5d2f3a64-8b0c-4c58-9d0e-7a6f2c1b9e11")


@events.subscribe(events.QuizGraded)
async def on_checkpoint_graded(session: AsyncSession, event: events.QuizGraded) -> None:
    attempt = await session.get(QuizAttempt, event.attempt_id)
    if attempt is None:
        return
    quiz = await session.get(Quiz, attempt.quiz_id)
    if quiz is None or quiz.kind != "CHECKPOINT":
        return

    processed = await LearningService(session).process_checkpoint_attempt(attempt, quiz)
    if processed is None:
        return

    points = PointsService(session)
    user_id = attempt.student_id
    offering_id = quiz.offering_id

    await points.award(
        user_id, Award("CHECKPOINT_DONE", "QUIZ_ATTEMPT", attempt.id, offering_id=offering_id)
    )
    if processed.total and Decimal(processed.correct) / Decimal(processed.total) >= HIGH_SCORE:
        await points.award(
            user_id, Award("CHECKPOINT_HIGH", "QUIZ_ATTEMPT", attempt.id, offering_id=offering_id)
        )
    if processed.improved:
        await points.award(
            user_id, Award("SKILL_IMPROVED", "QUIZ_ATTEMPT", attempt.id, offering_id=offering_id)
        )
    milestone = processed.streak.milestone
    if milestone is not None:
        started = processed.streak.state.started_on
        source = uuid.uuid5(_STREAK_NS, f"{user_id}:{offering_id}:{started}:{milestone}")
        await points.award(
            user_id, Award(f"STREAK_{milestone}", "STREAK", source, offering_id=offering_id)
        )
