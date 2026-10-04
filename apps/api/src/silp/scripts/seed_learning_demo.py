"""نمونهٔ حلقهٔ یادگیری روزانه — فقط توسعه (ADR-0036).

اجرا: ``python -m silp.scripts.seed_learning_demo``

روی نخستین ارائه: دو شایستگی با مفهوم، ۱۲ سؤال بانک، یک درس‌نامهٔ منتشرشده، یک چالش باز
(۴ سؤال از استخر ۱۲تایی)، و ثبت‌نام دانشجوی نمونه (۰۹۱۲۰۰۰۰۰۱۰) تا «امروز» و پیام‌ها را بتوانی
ببینی. بی‌اثر در تکرار. در ``ENVIRONMENT`` غیر از ``development`` با خطا خارج می‌شود.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from silp.core.config import get_settings
from silp.db.session import dispose_engine, session_scope
from silp.models.education import CourseOffering, Enrollment
from silp.models.identity import User
from silp.models.learning import Competency, Concept, Lesson
from silp.models.quiz import QuestionBankItem, Quiz
from silp.services.learning_service import LearningService
from silp.services.quiz_service import QuestionDraft, QuizService

INSTRUCTOR_MOBILE = "09120000002"
STUDENT_MOBILE = "09120000010"
OPTIONS = [{"id": "a", "text": "گزینهٔ نادرست"}, {"id": "b", "text": "گزینهٔ درست"}]

# (کد شایستگی، عنوان، کد مفهوم، عنوان مفهوم، سؤال‌ها)
PLAN: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "demo-capacity",
        "تحلیل ظرفیت",
        "demo-level-of-service",
        "سطح سرویس",
        (
            "ظرفیت یک معبر یعنی چه؟",
            "سطح سرویس چه چیزی را می‌سنجد؟",
            "کدام عامل ظرفیت را کم می‌کند؟",
            "نسبت حجم به ظرفیت چه می‌گوید؟",
            "تأثیر عرض خط بر ظرفیت چیست؟",
            "چرا ظرفیت تعدیل می‌شود؟",
        ),
    ),
    (
        "demo-flow",
        "جریان ترافیک",
        "demo-speed-density",
        "سرعت و چگالی",
        (
            "رابطهٔ سرعت و چگالی چیست؟",
            "چگالی بحرانی کجاست؟",
            "جریان آزاد یعنی چه؟",
            "موج ترافیکی چگونه شکل می‌گیرد؟",
            "حجم، سرعت و چگالی چه نسبتی دارند؟",
            "کدام نمودار رابطهٔ پایه را نشان می‌دهد؟",
        ),
    ),
)


async def main() -> int:
    if not get_settings().is_development:
        print("seed_learning_demo فقط در ENVIRONMENT=development اجرا می‌شود.", file=sys.stderr)
        return 1
    try:
        async with session_scope() as session:
            instructor = await session.scalar(select(User).where(User.mobile == INSTRUCTOR_MOBILE))
            student = await session.scalar(select(User).where(User.mobile == STUDENT_MOBILE))
            offering = await session.scalar(
                select(CourseOffering).order_by(CourseOffering.created_at).limit(1)
            )
            if instructor is None or student is None or offering is None:
                print("ابتدا `python -m silp.scripts.seed` را اجرا کن.", file=sys.stderr)
                return 1

            learning = LearningService(session)
            quizzes = QuizService(session)

            concept_ids = []
            for comp_code, comp_title, concept_code, concept_title, questions in PLAN:
                comp = await session.scalar(select(Competency).where(Competency.code == comp_code))
                if comp is None:
                    comp = await learning.create_competency(comp_code, comp_title)
                concept = await session.scalar(select(Concept).where(Concept.code == concept_code))
                if concept is None:
                    concept = await learning.create_concept(comp.id, concept_code, concept_title)
                concept_ids.append(concept.id)
                have = await session.scalar(
                    select(QuestionBankItem.id).where(QuestionBankItem.concept_id == concept.id)
                )
                if have is None:
                    for body in questions:
                        await quizzes.add_to_bank(
                            owner_id=instructor.id,
                            draft=QuestionDraft(
                                kind="SINGLE_CHOICE",
                                body=body,
                                payload={"options": OPTIONS, "correct": ["b"]},
                                explanation="توضیح: گزینهٔ «ب» درست است.",
                            ),
                            concept_id=concept.id,
                        )

            enrolled = await session.scalar(
                select(Enrollment.id).where(
                    Enrollment.offering_id == offering.id, Enrollment.student_id == student.id
                )
            )
            if enrolled is None:
                session.add(
                    Enrollment(offering_id=offering.id, student_id=student.id, status="ACTIVE")
                )
                await session.flush()

            lesson = await session.scalar(
                select(Lesson).where(
                    Lesson.offering_id == offering.id, Lesson.title_fa == "درس‌نامهٔ نمونه"
                )
            )
            if lesson is None:
                lesson = await learning.create_lesson(
                    offering.id,
                    instructor.id,
                    title_fa="درس‌نامهٔ نمونه",
                    body_md=(
                        "## ظرفیت و سطح سرویس\n\n"
                        "ظرفیت، بیشینهٔ جریانی است که یک معبر در شرایط مشخص می‌تواند عبور دهد.\n\n"
                        "- سطح سرویس کیفیت جریان را نشان می‌دهد.\n"
                        "- نسبت حجم به ظرفیت شاخص ساده‌ای برای ازدحام است.\n"
                    ),
                    est_minutes=5,
                    publish=True,
                )

            exists = await session.scalar(
                select(Quiz.id).where(Quiz.offering_id == offering.id, Quiz.kind == "CHECKPOINT")
            )
            if exists is None:
                now = datetime.now(UTC)
                await quizzes.create_checkpoint(
                    offering_id=offering.id,
                    created_by=instructor.id,
                    title_fa="چالش امروز",
                    lesson_id=lesson.id,
                    concept_ids=concept_ids,
                    draw_count=4,
                    opens_at=now - timedelta(minutes=10),
                    closes_at=now + timedelta(days=1),
                    duration_min=8,
                    publish=True,
                )
        print("نمونهٔ یادگیری روزانه آماده است. دانشجو: 09120000010 · کد ورود: 111111")
    finally:
        await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
