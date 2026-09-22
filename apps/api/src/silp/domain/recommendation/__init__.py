"""موتور توصیه‌گر — PRD §08.

| ماژول | مسئولیت |
|-------|---------|
| `schemas` | ساختارهای داده، بدون رفتار |
| `scorer` | شش زیرامتیاز و ترکیبشان — توابع خالص |
| `explainer` | تولید متن فارسی دلیل |
| `diversity` | بازچینش نتایج |
| `service` | هماهنگی: واکشی از دیتابیس، امتیازدهی، کش |

سه ماژول اول هیچ I/O ندارند و بدون دیتابیس قابل تست‌اند (§8.12).
"""

from silp.domain.recommendation.diversity import diversify, ensure_stretch
from silp.domain.recommendation.explainer import explain, with_reasons
from silp.domain.recommendation.schemas import (
    DEFAULT_WEIGHTS,
    AssetReq,
    Component,
    Goal,
    InterestRef,
    MatchResult,
    Polarity,
    ProjectKind,
    ProjectSpec,
    Reason,
    ReasonType,
    SkillReq,
    StudentContext,
    Verdict,
    Weights,
    WorkStyle,
)
from silp.domain.recommendation.scorer import score_project

__all__ = [
    "DEFAULT_WEIGHTS",
    "AssetReq",
    "Component",
    "Goal",
    "InterestRef",
    "MatchResult",
    "Polarity",
    "ProjectKind",
    "ProjectSpec",
    "Reason",
    "ReasonType",
    "SkillReq",
    "StudentContext",
    "Verdict",
    "Weights",
    "WorkStyle",
    "diversify",
    "ensure_stretch",
    "explain",
    "score_project",
    "with_reasons",
]
