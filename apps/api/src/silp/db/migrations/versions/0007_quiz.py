"""0007 — آزمون: آزمون، بانک سؤال، سؤال، تلاش، پاسخ، اعتراض

مرجع: PRD §4.5.
وظیفهٔ نقشهٔ راه: M4-01.

سه چیز اینجا در **دیتابیس** اعمال می‌شود، نه در اپلیکیشن، چون هر سه
تحت رقابت‌اند و لایهٔ سرویس نمی‌تواند تنها نگهبانشان باشد (§7.12):

| قاعده | ابزار |
|-------|-------|
| یک تلاش فعال در هر لحظه | ایندکس یکتای جزئی `idx_one_active_attempt` |
| `attempt_no` بدون تصادم | قید یکتای `(quiz_id, student_id, attempt_no)` |
| `quizzes.total_points` درست | تریگر روی `quiz_questions` |

چهار ستون فراتر از §4.5 افزوده شده — دلیل هرکدام کنار خودش:
`quizzes.results_published_at`، `quiz_attempts.graded_by`،
`quiz_attempts.auto_closed` و `quiz_answers.client_ts` (ADR-0011).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ZERO = sa.text("0")
EMPTY_JSONB = sa.text("'{}'::jsonb")
EMPTY_JSONB_ARRAY = sa.text("'[]'::jsonb")

QUESTION_KINDS = (
    "SINGLE_CHOICE",
    "MULTI_CHOICE",
    "TRUE_FALSE",
    "SHORT_ANSWER",
    "NUMERIC",
    "ESSAY",
    "MATCHING",
)
QUIZ_STATUSES = ("DRAFT", "PUBLISHED", "CLOSED")
RESULT_VISIBILITIES = ("IMMEDIATE", "AFTER_CLOSE", "MANUAL")
ATTEMPT_STATUSES = ("IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "GRADED", "VOIDED")
APPEAL_STATUSES = ("OPEN", "ACCEPTED", "REJECTED")

MIN_DURATION_MIN = 1
MAX_DURATION_MIN = 300
MAX_ATTEMPTS = 10


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_quizzes()
    _create_question_bank()
    _create_quiz_questions()
    _create_total_points_trigger()
    _create_attempts()
    _create_answers()
    _create_appeals()


# ── آزمون ──────────────────────────────────────────────────────────────
def _create_quizzes() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("passing_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("shuffle_options", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column(
            "result_visibility",
            sa.Text(),
            server_default=sa.text("'AFTER_CLOSE'"),
            nullable=False,
        ),
        sa.Column("show_correct_answers", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        # مشتق — با تریگر به‌روز می‌شود، نه با اپلیکیشن (§7.12).
        sa.Column("total_points", sa.Numeric(6, 2), server_default=ZERO, nullable=False),
        # فراتر از §4.5: لحظهٔ انتشار نتیجه. مهلت ۷ روزهٔ اعتراض (§7.3)
        # از همین می‌شمارد و بدون آن قابل محاسبه نیست — `closes_at` کافی
        # نیست چون در حالت `MANUAL` استاد هر وقت بخواهد منتشر می‌کند.
        sa.Column("results_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_quizzes"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_quizzes_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["course_weeks.id"],
            name="fk_quizzes_week_id_course_weeks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_quizzes_created_by_users"),
        sa.CheckConstraint("closes_at > opens_at", name="ck_quizzes_window"),
        sa.CheckConstraint(
            f"duration_min BETWEEN {MIN_DURATION_MIN} AND {MAX_DURATION_MIN}",
            name="ck_quizzes_duration_range",
        ),
        sa.CheckConstraint(
            f"max_attempts BETWEEN 1 AND {MAX_ATTEMPTS}", name="ck_quizzes_max_attempts_range"
        ),
        sa.CheckConstraint(
            "passing_score IS NULL OR passing_score >= 0", name="ck_quizzes_passing_score_positive"
        ),
        sa.CheckConstraint(
            _in_list("result_visibility", RESULT_VISIBILITIES),
            name="ck_quizzes_result_visibility_valid",
        ),
        sa.CheckConstraint(_in_list("status", QUIZ_STATUSES), name="ck_quizzes_status_valid"),
    )
    op.create_index("idx_quizzes_offering", "quizzes", ["offering_id", "status"])
    op.create_index(
        "idx_quizzes_week", "quizzes", ["week_id"], postgresql_where=sa.text("week_id IS NOT NULL")
    )
    # کار پس‌زمینهٔ بستن خودکار (§7.11) آزمون‌های باز را هر دقیقه می‌بیند؛
    # بدون این ایندکس، پیمایش کل جدول در هر اجرا.
    op.create_index(
        "idx_quizzes_open_window",
        "quizzes",
        ["closes_at"],
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    op.execute("SELECT attach_updated_at('quizzes')")


# ── بانک سؤال ──────────────────────────────────────────────────────────
def _create_question_bank() -> None:
    op.create_table(
        "question_bank",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_question_bank"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_question_bank_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name="fk_question_bank_course_id_courses"
        ),
        sa.CheckConstraint(_in_list("kind", QUESTION_KINDS), name="ck_question_bank_kind_valid"),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 5",
            name="ck_question_bank_difficulty_range",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_question_bank_payload_is_object"
        ),
        sa.CheckConstraint("usage_count >= 0", name="ck_question_bank_usage_count_positive"),
    )
    # انتخاب تصادفی N سؤال از یک دسته (FR-QUIZ-01) روی همین سه ستون
    # فیلتر می‌کند.
    op.create_index(
        "idx_question_bank_pick",
        "question_bank",
        ["course_id", "category", "difficulty"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_question_bank_owner", "question_bank", ["owner_id"])
    op.execute("SELECT attach_updated_at('question_bank')")


# ── سؤال‌های یک آزمون ──────────────────────────────────────────────────
def _create_quiz_questions() -> None:
    op.create_table(
        "quiz_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        # منشأ، اگر از بانک آمده. کپی است نه ارجاع: ویرایش بعدی سؤال در
        # بانک نباید آزمونِ برگزارشده را عوض کند.
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("points", sa.Numeric(5, 2), server_default=sa.text("1"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_questions"),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name="fk_quiz_questions_quiz_id_quizzes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["question_bank.id"],
            name="fk_quiz_questions_bank_id_question_bank",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(_in_list("kind", QUESTION_KINDS), name="ck_quiz_questions_kind_valid"),
        sa.CheckConstraint("points > 0", name="ck_quiz_questions_points_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_quiz_questions_payload_is_object"
        ),
    )
    op.create_index("idx_quiz_questions_quiz", "quiz_questions", ["quiz_id", "sort_order"])


def _create_total_points_trigger() -> None:
    """`quizzes.total_points` را دیتابیس نگه می‌دارد، نه اپلیکیشن (§7.12).

    دلیلش این است که سؤال از چند جا اضافه و حذف می‌شود (ویرایشگر، کپی از
    بانک، حذف آبشاری آزمون) و یک جای فراموش‌شده یعنی بارم کل غلط در
    فهرست آزمون‌ها. `COALESCE` برای وقتی است که آخرین سؤال حذف شود.
    """
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
    op.execute(
        """
        CREATE TRIGGER trg_quiz_questions_total_points
        AFTER INSERT OR UPDATE OF points, quiz_id OR DELETE ON quiz_questions
        FOR EACH ROW EXECUTE FUNCTION sync_quiz_total_points();
        """
    )


# ── تلاش ───────────────────────────────────────────────────────────────
def _create_attempts() -> None:
    op.create_table(
        "quiz_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'IN_PROGRESS'"), nullable=False),
        sa.Column("question_order", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        # مرجع زمان، سروری و تغییرناپذیر — §7.3 قاعدهٔ ۱.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("manual_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("total_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("is_provisional", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column(
            "integrity_events", postgresql.JSONB(), server_default=EMPTY_JSONB_ARRAY, nullable=False
        ),
        # فراتر از §4.5: چه کسی تصحیح دستی را تمام کرد. اعتراض به نمره
        # (§7.3) بدون این نمی‌داند پاسخ را از چه کسی بخواهد.
        sa.Column("graded_by", postgresql.UUID(as_uuid=True), nullable=True),
        # فراتر از §4.5: آیا زمان تمام شد یا دانشجو خودش ارسال کرد؟
        # §7.3 هر دو مسیر را به `GRADED` می‌رساند، پس پس از تصحیح، این
        # تفاوت از `status` قابل بازیابی نیست — و صفحهٔ نتیجه باید
        # بتواند بگوید «زمانت تمام شد»، نه «ارسال کردی». ADR-0011.
        sa.Column("auto_closed", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_attempts"),
        sa.ForeignKeyConstraint(
            ["quiz_id"], ["quizzes.id"], name="fk_quiz_attempts_quiz_id_quizzes"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_quiz_attempts_student_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["graded_by"], ["users.id"], name="fk_quiz_attempts_graded_by_users"
        ),
        sa.UniqueConstraint(
            "quiz_id",
            "student_id",
            "attempt_no",
            name="uq_quiz_attempts_quiz_id_student_id_attempt_no",
        ),
        sa.CheckConstraint(
            _in_list("status", ATTEMPT_STATUSES), name="ck_quiz_attempts_status_valid"
        ),
        sa.CheckConstraint("attempt_no > 0", name="ck_quiz_attempts_attempt_no_positive"),
        sa.CheckConstraint("expires_at > started_at", name="ck_quiz_attempts_window"),
        sa.CheckConstraint(
            "jsonb_typeof(integrity_events) = 'array'",
            name="ck_quiz_attempts_integrity_events_is_array",
        ),
    )
    # دو کلیک سریع روی «شروع آزمون» فقط یک تلاش می‌سازد — §7.12.
    op.create_index(
        "idx_one_active_attempt",
        "quiz_attempts",
        ["quiz_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'IN_PROGRESS'"),
    )
    # §4.5 این ایندکس را روی `status IN ('SUBMITTED','AUTO_SUBMITTED')`
    # گذاشته بود. چون تصحیح خودکار **هم‌زمان** با ارسال انجام می‌شود،
    # تلاش در آن دو وضعیت نمی‌ماند و آن ایندکس همیشه خالی می‌ماند.
    # صف واقعیِ تصحیح دستی `is_provisional` است — ADR-0011.
    op.create_index(
        "idx_attempts_grading",
        "quiz_attempts",
        ["quiz_id"],
        postgresql_where=sa.text("is_provisional"),
    )
    op.create_index("idx_attempts_student", "quiz_attempts", ["student_id", "quiz_id"])
    # کار پس‌زمینهٔ بستن خودکار هر ۶۰ ثانیه فقط همین را می‌پرسد: کدام
    # تلاشِ در جریان منقضی شده؟ (§7.3 قاعدهٔ ۲)
    op.create_index(
        "idx_attempts_expiring",
        "quiz_attempts",
        ["expires_at"],
        postgresql_where=sa.text("status = 'IN_PROGRESS'"),
    )


# ── پاسخ ───────────────────────────────────────────────────────────────
def _create_answers() -> None:
    op.create_table(
        "quiz_answers",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.Column("is_flagged", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("auto_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("manual_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("grader_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        # فراتر از §4.5: زمانی که **کلاینت** ادعا می‌کند پاسخ را نوشته.
        # §7.3 قاعدهٔ ۳ برای پذیرش پاسخِ دیررسیده به آن نیاز دارد، و
        # همگام‌سازی پس از آفلاین (§5.6) با همین تصمیم می‌گیرد کدام
        # نسخهٔ یک پاسخ تازه‌تر است.
        sa.Column("client_ts", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id", "question_id", name="pk_quiz_answers"),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_quiz_answers_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["quiz_questions.id"],
            name="fk_quiz_answers_question_id_quiz_questions",
        ),
        sa.ForeignKeyConstraint(
            ["grader_id"], ["users.id"], name="fk_quiz_answers_grader_id_users"
        ),
    )
    # صف تصحیح تشریحی «بر اساس سؤال» است، نه بر اساس دانشجو (M4-10):
    # استاد یک سؤال را برای سی نفر پشت سر هم می‌خواند.
    op.create_index(
        "idx_quiz_answers_grading_queue",
        "quiz_answers",
        ["question_id", "attempt_id"],
        postgresql_where=sa.text("manual_score IS NULL"),
    )


# ── اعتراض به نمره ─────────────────────────────────────────────────────
def _create_appeals() -> None:
    op.create_table(
        "grade_appeals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_grade_appeals"),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_grade_appeals_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["quiz_questions.id"],
            name="fk_grade_appeals_question_id_quiz_questions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_grade_appeals_student_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name="fk_grade_appeals_resolved_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", APPEAL_STATUSES), name="ck_grade_appeals_status_valid"
        ),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_grade_appeals_reason_not_blank"),
        # وضعیت و لحظهٔ رسیدگی از هم جدا نمی‌افتند — همان الگوی ADR-0007.
        sa.CheckConstraint(
            "(status = 'OPEN') = (resolved_at IS NULL)", name="ck_grade_appeals_resolution_paired"
        ),
    )
    # یک اعتراض باز برای هر (تلاش، سؤال) — اعتراض دوباره به همان سؤال،
    # صف را شلوغ می‌کند بی‌آنکه حرف تازه‌ای بزند.
    op.create_index(
        "idx_one_open_appeal",
        "grade_appeals",
        ["attempt_id", "question_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN' AND question_id IS NOT NULL"),
    )
    op.create_index(
        "idx_one_open_overall_appeal",
        "grade_appeals",
        ["attempt_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN' AND question_id IS NULL"),
    )
    op.create_index("idx_grade_appeals_student", "grade_appeals", ["student_id", "status"])


def downgrade() -> None:
    op.drop_table("grade_appeals")
    op.drop_table("quiz_answers")
    op.drop_table("quiz_attempts")
    op.execute("DROP TRIGGER IF EXISTS trg_quiz_questions_total_points ON quiz_questions")
    op.execute("DROP FUNCTION IF EXISTS sync_quiz_total_points()")
    op.drop_table("quiz_questions")
    op.execute("DROP TRIGGER IF EXISTS trg_question_bank_updated ON question_bank")
    op.drop_table("question_bank")
    op.execute("DROP TRIGGER IF EXISTS trg_quizzes_updated ON quizzes")
    op.drop_table("quizzes")
