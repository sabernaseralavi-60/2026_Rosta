"""هم‌تیمی مکمل — PRD §8.14، FR-TEAM-01، ADR-0015. منطق خالص.

«همان چارچوب توصیه‌گر، با تغییر جهت: به‌جای "چقدر دانشجو به پروژه
می‌خورد"، "چقدر این فرد به **کمبود** تیم می‌خورد".»

```
gap_skills = مهارت‌های لازم پروژه که هیچ عضو فعلی در سطح کافی ندارد

             Σ_{s ∈ gap} w_s × fit(candidate, s)
complement = ──────────────────────────────────── × 100
                     Σ_{s ∈ gap} w_s
```

`fit` همان `skill_fit` توصیه‌گر است (§8.2) تا «سطح کافی» در دو جای سامانه
دو معنا نداشته باشد. سپس سه ضریب تعدیل §8.14 اعمال می‌شود.

بدون پروژه، «تیم تو» یعنی خودت: نتیجه عدد مکملیت ندارد (کمبودی تعریف
نشده)، فقط فهرست مهارت‌هایی که این فرد در آن‌ها از تو قوی‌تر است.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from silp.domain.recommendation.schemas import SkillReq, StudentContext
from silp.domain.recommendation.scorer import skill_fit
from silp.domain.text import join_fa, to_persian_digits

MAX_SCORE = 100.0

#: §8.14 «نرخ تکمیل بالا ⇒ ضریب ۱.۱». «بالا» یعنی دست‌کم ۸۰٪، و نرخ فقط
#: از دو پروژهٔ به‌پایان‌رسیده به بالا معنا دارد — یک پروژه آمار نیست.
COMPLETION_FACTOR = 1.10
COMPLETION_RATE_MIN = 0.8
COMPLETION_SAMPLE_MIN = 2
#: §8.14 «درس مشترک (ضریب ۱.۰۵)».
SHARED_COURSE_FACTOR = 1.05
#: در دسترس بودن — همان آستانهٔ راحتی §8.5 (نسبت ۰٫۸)، با کف ۰٫۵: کمبود
#: وقت مکملیت را نصف می‌کند، ولی مهارتی را که تیم ندارد پنهان نمی‌کند.
AVAILABILITY_COMFORT = 0.8
AVAILABILITY_FLOOR = 0.5

#: بدون پروژه — «قوی‌تر از تو» یعنی دست‌کم سطح ۳ در مهارتی که تو زیر ۳ هستی.
STRONG_LEVEL = 3
MAX_REASON_SKILLS = 3


@dataclass(frozen=True, slots=True)
class Need:
    """یک مهارت لازم پروژه — همان ردیف `project_required_skills`."""

    skill_id: uuid.UUID
    title_fa: str
    min_level: int
    weight: int = 1


@dataclass(frozen=True, slots=True)
class Candidate:
    user_id: uuid.UUID
    skills: Mapping[uuid.UUID, int]
    verified_skills: frozenset[uuid.UUID] = frozenset()
    weekly_hours: int | None = None
    completed_projects: int = 0
    dropped_projects: int = 0
    shares_course: bool = False

    @property
    def completion_rate(self) -> float | None:
        finished = self.completed_projects + self.dropped_projects
        if finished < COMPLETION_SAMPLE_MIN:
            return None
        return self.completed_projects / finished


@dataclass(frozen=True, slots=True)
class CoveredSkill:
    title_fa: str
    level: int
    verified: bool


@dataclass(frozen=True, slots=True)
class Complement:
    score: float
    covered: tuple[CoveredSkill, ...]
    reason: str


def team_gaps(needs: Sequence[Need], team_levels: Mapping[uuid.UUID, int]) -> list[Need]:
    """مهارت‌هایی که هیچ عضو فعلی در سطح لازم ندارد.

    `team_levels` بیشینهٔ سطح هر مهارت در میان اعضای فعال است. سطح
    تأییدنشده هم حساب می‌شود: پرسش این است که «تیم کسی را دارد؟»، نه
    «ادعایش تأیید شده؟».
    """
    return [n for n in needs if team_levels.get(n.skill_id, 0) < n.min_level]


def _fit(candidate: Candidate, need: Need) -> float:
    ctx = StudentContext(
        user_id=candidate.user_id,
        skills=dict(candidate.skills),
        verified_skills=candidate.verified_skills,
    )
    return skill_fit(
        ctx,
        SkillReq(
            skill_id=need.skill_id,
            title_fa=need.title_fa,
            min_level=need.min_level,
            weight=need.weight,
        ),
    )


def availability_factor(weekly_hours: int | None, commitment_hpw: int | None) -> float:
    if weekly_hours is None or not commitment_hpw:
        return 1.0
    ratio = weekly_hours / commitment_hpw
    if ratio >= AVAILABILITY_COMFORT:
        return 1.0
    return max(AVAILABILITY_FLOOR, ratio / AVAILABILITY_COMFORT)


def complement(
    candidate: Candidate, gaps: Sequence[Need], *, commitment_hpw: int | None = None
) -> Complement | None:
    """مکملیت یک نامزد برای کمبودهای تیم. `None` یعنی تیم کمبودی ندارد."""
    if not gaps:
        return None
    total_weight = sum(max(n.weight, 0) for n in gaps)
    if total_weight <= 0:
        return None

    weighted = sum(max(n.weight, 0) * _fit(candidate, n) for n in gaps)
    score = weighted / total_weight * MAX_SCORE
    score *= availability_factor(candidate.weekly_hours, commitment_hpw)
    rate = candidate.completion_rate
    if rate is not None and rate >= COMPLETION_RATE_MIN:
        score *= COMPLETION_FACTOR
    if candidate.shares_course:
        score *= SHARED_COURSE_FACTOR
    score = round(max(0.0, min(MAX_SCORE, score)), 1)

    ordered = sorted(gaps, key=lambda n: (-n.weight, n.title_fa))
    covered = tuple(
        CoveredSkill(
            title_fa=n.title_fa,
            level=candidate.skills[n.skill_id],
            verified=n.skill_id in candidate.verified_skills,
        )
        for n in ordered
        if candidate.skills.get(n.skill_id, 0) >= n.min_level
    )
    return Complement(score=score, covered=covered, reason=_reason(candidate, ordered, covered))


def _reason(candidate: Candidate, gaps: Sequence[Need], covered: Sequence[CoveredSkill]) -> str:
    """§8.14 «علی مهارت GIS در سطح ۴ دارد که هیچ‌کس در تیم ندارد.»"""
    if len(covered) == 1:
        skill = covered[0]
        level = to_persian_digits(str(skill.level))
        return f"مهارت {skill.title_fa} را در سطح {level} دارد که هیچ‌کس در تیم ندارد."
    if covered:
        titles = [c.title_fa for c in covered[:MAX_REASON_SKILLS]]
        rest = len(covered) - len(titles)
        tail = f" و {to_persian_digits(str(rest))} مهارت دیگر" if rest else ""
        return f"مهارت‌های {join_fa(titles)}{tail} را دارد که هیچ‌کس در تیم ندارد."
    partial = [n for n in gaps if candidate.skills.get(n.skill_id, 0) > 0]
    if partial:
        need = max(partial, key=lambda n: candidate.skills[n.skill_id] - n.min_level)
        have = to_persian_digits(str(candidate.skills[need.skill_id]))
        want = to_persian_digits(str(need.min_level))
        return f"در {need.title_fa} به کمبود تیم نزدیک است (سطح {have} از {want})."
    return "هیچ‌کدام از مهارت‌هایی را که تیم کم دارد، ثبت نکرده است."


def stronger_skills(
    candidate: Candidate,
    my_skills: Mapping[uuid.UUID, int],
    titles: Mapping[uuid.UUID, str],
) -> list[CoveredSkill]:
    """بدون پروژه: مهارت‌هایی که این فرد در آن‌ها از جستجوکننده قوی‌تر است."""
    result = [
        CoveredSkill(
            title_fa=titles.get(skill_id, "مهارت"),
            level=level,
            verified=skill_id in candidate.verified_skills,
        )
        for skill_id, level in candidate.skills.items()
        if level >= STRONG_LEVEL and my_skills.get(skill_id, 0) < STRONG_LEVEL
    ]
    result.sort(key=lambda c: (-c.level, not c.verified, c.title_fa))
    return result


def stronger_reason(skills: Sequence[CoveredSkill]) -> str | None:
    if not skills:
        return None
    titles = [s.title_fa for s in skills[:MAX_REASON_SKILLS]]
    return f"در {join_fa(titles)} از تو قوی‌تر است."


__all__ = [
    "Candidate",
    "Complement",
    "CoveredSkill",
    "Need",
    "availability_factor",
    "complement",
    "stronger_reason",
    "stronger_skills",
    "team_gaps",
]
