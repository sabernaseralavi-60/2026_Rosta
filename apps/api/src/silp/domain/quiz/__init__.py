"""دامنهٔ آزمون — PRD §4.5، §5.6، §7.3، FR-QUIZ-01..05.

| ماژول | مسئولیت |
|-------|---------|
| `schemas` | ساختار سؤال و نتیجهٔ تصحیح، بدون رفتار |
| `payload` | پارس `payload` و **پنهان‌کردن کلید پاسخ** |
| `normalize` | نرمال‌سازی پاسخ کوتاه فارسی |
| `grading` | قواعد نمره‌دهی شش نوع سؤال بسته |
| `shuffle` | ترتیب قطعیِ درهم سؤال و گزینه |
| `timing` | پنجرهٔ زمانی، پذیرش پاسخ، مهلت اعتراض |

هیچ‌کدام I/O ندارند: نه دیتابیس، نه ساعت سیستم، نه تصادف. هر تابعی که
به «حالا» نیاز دارد `now` را آرگومان می‌گیرد. هماهنگی با دیتابیس در
`silp.services.quiz_service` و `attempt_service` است، نه اینجا.

این خلوص شرطِ تست‌های اجباری M4 (§13) است — نمره‌ای که فقط با یک
دیتابیس و سی سطر داده قابل بررسی باشد، عملاً بررسی نمی‌شود.
"""

from silp.domain.quiz.grading import (
    grade_answer,
    grade_attempt,
    needs_manual_grading,
    quantize,
    total_auto_score,
)
from silp.domain.quiz.normalize import answers_match, normalize_answer
from silp.domain.quiz.payload import (
    InvalidQuestionPayload,
    parse_question,
    public_payload,
    review_payload,
    validate_payload,
)
from silp.domain.quiz.schemas import (
    AUTO_GRADED_KINDS,
    CHOICE_KINDS,
    QUESTION_KIND_TITLE_FA,
    GradedAnswer,
    MatchPair,
    Option,
    Question,
    QuestionKind,
)
from silp.domain.quiz.shuffle import option_order, question_order, shuffled_ids
from silp.domain.quiz.timing import (
    APPEAL_WINDOW,
    NETWORK_GRACE,
    QUIZ_AVAILABILITY_TITLE_FA,
    WARN_AT_SECONDS,
    AttemptWindow,
    QuizAvailability,
    accepts_answer,
    appeal_window_open,
    availability,
    compute_expires_at,
)

__all__ = [
    "APPEAL_WINDOW",
    "AUTO_GRADED_KINDS",
    "CHOICE_KINDS",
    "NETWORK_GRACE",
    "QUESTION_KIND_TITLE_FA",
    "QUIZ_AVAILABILITY_TITLE_FA",
    "WARN_AT_SECONDS",
    "AttemptWindow",
    "GradedAnswer",
    "InvalidQuestionPayload",
    "MatchPair",
    "Option",
    "Question",
    "QuestionKind",
    "QuizAvailability",
    "accepts_answer",
    "answers_match",
    "appeal_window_open",
    "availability",
    "compute_expires_at",
    "grade_answer",
    "grade_attempt",
    "needs_manual_grading",
    "normalize_answer",
    "option_order",
    "parse_question",
    "public_payload",
    "quantize",
    "question_order",
    "review_payload",
    "shuffled_ids",
    "total_auto_score",
    "validate_payload",
]
