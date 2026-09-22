"""دامنهٔ گیمیفیکیشن — PRD §9، FR-GAM-01..04.

| ماژول | مسئولیت |
|-------|---------|
| `levels` | آستانه و عنوان سطح از امتیاز کل (§9.4) |
| `formulas` | ضریب هر قاعده و ضرایب تعدیل (§9.2، §9.3) |
| `badges` | ارزیاب معیار نشان و پیشرفت به‌سوی آن (§9.5) |
| `learning_score` | نمرهٔ یادگیری ۰ تا ۱۰۰ هر ارائه (§9.6) |

هیچ‌کدام I/O ندارند. دفتر کل، سقف‌ها و بی‌اثری در تکرار در
`silp.services.points_service` هستند، چون به دیتابیس و قفل نیاز دارند.
"""

from silp.domain.gamification.badges import (
    BadgeFacts,
    InvalidCriteria,
    Progress,
    count_key,
    evaluate,
    longest_weekly_streak,
    validate,
)
from silp.domain.gamification.levels import LevelProgress, level_for, progress, threshold

__all__ = [
    "BadgeFacts",
    "InvalidCriteria",
    "LevelProgress",
    "Progress",
    "count_key",
    "evaluate",
    "level_for",
    "longest_weekly_streak",
    "progress",
    "threshold",
    "validate",
]
