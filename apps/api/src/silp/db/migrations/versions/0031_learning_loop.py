"""0031 — حلقهٔ یادگیری روزانه: درس‌نامه، چالش، شایستگی، استمرار

مرجع: ADR-0036 §۲.۱–۲.۳، §۵، §۶.

* `modules`، `lessons` — درس‌نامهٔ روزانه زیر ارائه (و اختیاری زیر هفته).
* `topics` → `concepts` → `competencies` — زنجیرهٔ دانش؛ سؤال به **مفهوم** وصل می‌شود.
  (نام فارسی `competency` «شایستگی» است تا با `skills` پرسشنامهٔ نیمرخ قاطی نشود.)
* `quizzes.kind` (`EXAM`/`QUIZ`/`CHECKPOINT`)، `lesson_id`، `draw_count` — چالش روزانه
  همان موتور آزمون است. با `draw_count` هر تلاش n سؤال از استخر می‌گیرد؛ جمع نمره‌ی
  آزمون آن‌وقت `draw_count × نمرهٔ هر سؤال` است (سؤال‌های استخر نمرهٔ یکسان دارند).
* `question_bank.concept_id`، `quiz_questions.concept_id` (کپیِ منجمد هنگام کپی از بانک).
* `competency_mastery`، `streaks` — **مشتق‌اند** و از `quiz_answers` بازسازی‌پذیرند.
* قواعد امتیاز چالش و استمرار.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
UUID = postgresql.UUID(as_uuid=True)

# (کد، عنوان، دسته، امتیاز پایه، فرمول، سقف روزانه، سقف هفتگی)
RULES: tuple[tuple[str, str, str, str, str | None, int | None, int | None], ...] = (
    ("CHECKPOINT_DONE", "تکمیل چالش روزانه", "LEARNING", "5", "یک‌بار برای هر چالش", 30, None),
    ("CHECKPOINT_HIGH", "نمرهٔ بالا در چالش", "LEARNING", "3", "۸۰٪ یا بیشتر", 15, None),
    ("SKILL_IMPROVED", "بهبود شایستگی", "LEARNING", "5", "رشد دست‌کم ۱۰٪ نسبت به پیش", 15, None),
    ("STREAK_7", "هفت روز استمرار", "LEARNING", "20", "هفت روز پیاپی چالش", None, None),
    ("STREAK_30", "سی روز استمرار", "LEARNING", "100", "سی روز پیاپی چالش", None, None),
)


def upgrade() -> None:
    op.create_table(
        "modules",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", UUID, nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_modules"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_modules_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_modules_offering", "modules", ["offering_id", "sort_order"])

    op.create_table(
        "lessons",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", UUID, nullable=False),
        sa.Column("module_id", UUID, nullable=True),
        sa.Column("week_id", UUID, nullable=True),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("est_minutes", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_lessons"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_lessons_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"], ["modules.id"], name="fk_lessons_module_id_modules", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["course_weeks.id"],
            name="fk_lessons_week_id_course_weeks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_lessons_created_by_users"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED')", name="status_valid"),
        sa.CheckConstraint("est_minutes BETWEEN 1 AND 120", name="est_minutes_range"),
        sa.CheckConstraint("length(body_md) <= 60000", name="body_length"),
    )
    op.create_index("idx_lessons_offering", "lessons", ["offering_id", "status", "publish_at"])

    op.create_table(
        "topics",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_topics"),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name="fk_topics_course_id_courses", ondelete="CASCADE"
        ),
    )
    op.create_table(
        "competencies",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_competencies"),
        sa.UniqueConstraint("code", name="uq_competencies_code"),
    )
    op.create_table(
        "concepts",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("competency_id", UUID, nullable=False),
        sa.Column("topic_id", UUID, nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_concepts"),
        sa.UniqueConstraint("code", name="uq_concepts_code"),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_concepts_competency_id_competencies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"], name="fk_concepts_topic_id_topics", ondelete="SET NULL"
        ),
    )
    op.create_index("idx_concepts_competency", "concepts", ["competency_id"])

    # ── سؤال → مفهوم؛ آزمون → نوع/درس/استخر ────────────────────────────
    op.add_column("question_bank", sa.Column("concept_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_question_bank_concept_id_concepts",
        "question_bank",
        "concepts",
        ["concept_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("quiz_questions", sa.Column("concept_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_quiz_questions_concept_id_concepts",
        "quiz_questions",
        "concepts",
        ["concept_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_quiz_questions_concept",
        "quiz_questions",
        ["concept_id"],
        postgresql_where=sa.text("concept_id IS NOT NULL"),
    )

    op.add_column(
        "quizzes", sa.Column("kind", sa.Text(), server_default=sa.text("'QUIZ'"), nullable=False)
    )
    op.add_column("quizzes", sa.Column("lesson_id", UUID, nullable=True))
    op.add_column("quizzes", sa.Column("draw_count", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_quizzes_lesson_id_lessons",
        "quizzes",
        "lessons",
        ["lesson_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint("kind_valid", "quizzes", "kind IN ('EXAM', 'QUIZ', 'CHECKPOINT')")
    op.create_check_constraint(
        "draw_count_range", "quizzes", "draw_count IS NULL OR draw_count BETWEEN 1 AND 100"
    )
    op.create_index(
        "idx_quizzes_lesson",
        "quizzes",
        ["lesson_id"],
        postgresql_where=sa.text("lesson_id IS NOT NULL"),
    )

    # جمع نمره با استخر: n × کمترین نمرهٔ سؤال (سرویس یکسان‌بودن نمره‌ها را تضمین می‌کند).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION recompute_quiz_total(target UUID) RETURNS VOID AS $$
          UPDATE quizzes q SET total_points = COALESCE(
            CASE WHEN q.draw_count IS NOT NULL
              THEN q.draw_count * (SELECT MIN(points) FROM quiz_questions WHERE quiz_id = target)
              ELSE (SELECT SUM(points) FROM quiz_questions WHERE quiz_id = target)
            END, 0)
          WHERE q.id = target;
        $$ LANGUAGE sql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_quiz_total_points() RETURNS TRIGGER AS $$
        BEGIN
          PERFORM recompute_quiz_total(COALESCE(NEW.quiz_id, OLD.quiz_id));
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_quiz_total_on_draw() RETURNS TRIGGER AS $$
        BEGIN
          PERFORM recompute_quiz_total(NEW.id);
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quizzes_total_on_draw
        AFTER INSERT OR UPDATE OF draw_count ON quizzes
        FOR EACH ROW EXECUTE FUNCTION sync_quiz_total_on_draw();
        """
    )

    # ── مشتق‌ها ────────────────────────────────────────────────────────
    op.create_table(
        "competency_mastery",
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("competency_id", UUID, nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence_n", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "competency_id", name="pk_competency_mastery"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_competency_mastery_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_competency_mastery_competency_id_competencies",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
    )
    op.create_table(
        "streaks",
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("offering_id", UUID, nullable=False),
        sa.Column("current", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("longest", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("last_day", sa.Date(), nullable=True),
        sa.Column("freeze_week", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "offering_id", name="pk_streaks"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_streaks_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_streaks_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
    )

    # یک ردیف به‌ازای هر تلاشِ چالشِ پردازش‌شده: هم تاریخچهٔ داشبورد، هم قفل بی‌اثری —
    # `QuizGraded` برای تصحیح دستی و اعتراض دوباره می‌آید ولی شایستگی دوبار شمرده نمی‌شود.
    op.create_table(
        "checkpoint_results",
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("quiz_id", UUID, nullable=False),
        sa.Column("offering_id", UUID, nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("attempt_id", name="pk_checkpoint_results"),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_checkpoint_results_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_checkpoint_results_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name="fk_checkpoint_results_quiz_id_quizzes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_checkpoint_results_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("correct BETWEEN 0 AND total", name="counts_valid"),
    )
    op.create_index("idx_checkpoint_results_user_day", "checkpoint_results", ["user_id", "day"])

    op.bulk_insert(
        sa.table(
            "point_rules",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("category", sa.Text),
            sa.column("base_points", sa.Numeric),
            sa.column("formula", sa.Text),
            sa.column("daily_cap", sa.Integer),
            sa.column("weekly_cap", sa.Integer),
        ),
        [
            {
                "code": code,
                "title_fa": title,
                "category": category,
                "base_points": base,
                "formula": formula,
                "daily_cap": daily,
                "weekly_cap": weekly,
            }
            for code, title, category, base, formula, daily, weekly in RULES
        ],
    )


def downgrade() -> None:
    codes = ", ".join(f"'{r[0]}'" for r in RULES)
    op.execute(f"DELETE FROM point_entries WHERE rule_code IN ({codes})")
    op.execute(f"DELETE FROM point_rules WHERE code IN ({codes})")
    op.drop_table("checkpoint_results")
    op.drop_table("streaks")
    op.drop_table("competency_mastery")
    op.execute("DROP TRIGGER IF EXISTS trg_quizzes_total_on_draw ON quizzes")
    op.execute("DROP FUNCTION IF EXISTS sync_quiz_total_on_draw()")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_quiz_total_points() RETURNS TRIGGER AS $$
        DECLARE
          target UUID := COALESCE(NEW.quiz_id, OLD.quiz_id);
        BEGIN
          UPDATE quizzes SET total_points = COALESCE(
            (SELECT SUM(points) FROM quiz_questions WHERE quiz_id = target), 0
          ) WHERE id = target;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS recompute_quiz_total(UUID)")
    op.drop_index("idx_quizzes_lesson", table_name="quizzes")
    op.drop_constraint("draw_count_range", "quizzes", type_="check")
    op.drop_constraint("kind_valid", "quizzes", type_="check")
    op.drop_constraint("fk_quizzes_lesson_id_lessons", "quizzes", type_="foreignkey")
    op.drop_column("quizzes", "draw_count")
    op.drop_column("quizzes", "lesson_id")
    op.drop_column("quizzes", "kind")
    op.drop_index("idx_quiz_questions_concept", table_name="quiz_questions")
    op.drop_constraint(
        "fk_quiz_questions_concept_id_concepts", "quiz_questions", type_="foreignkey"
    )
    op.drop_column("quiz_questions", "concept_id")
    op.drop_constraint("fk_question_bank_concept_id_concepts", "question_bank", type_="foreignkey")
    op.drop_column("question_bank", "concept_id")
    op.drop_table("concepts")
    op.drop_table("competencies")
    op.drop_table("topics")
    op.drop_table("lessons")
    op.drop_table("modules")
