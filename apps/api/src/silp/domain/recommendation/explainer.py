"""تولید دلیل فارسی برای هر پیشنهاد — PRD §8.10.

**قاعدهٔ سند:** متن دلیل در بک‌اند تولید می‌شود، نه فرانت‌اند. منطق توضیح
باید یکجا باشد و در تست پوشش داده شود؛ اگر کلاینت متن بسازد، وب و
اپلیکیشن موبایل آینده دو روایت متفاوت از یک عدد می‌دهند.

«سهم» (`contribution`) یعنی این عامل چند واحد از امتیاز ۰ تا ۱۰۰ نهایی را
ساخته یا خورده است. دلایل بر همین اساس مرتب می‌شوند، نه بر اساس ترتیب
تعریف — §8.10.
"""

from __future__ import annotations

from dataclasses import replace

from silp.domain.recommendation.schemas import (
    GOAL_TITLE_FA,
    MAX_SCORE,
    Component,
    MatchResult,
    Polarity,
    Reason,
    ReasonType,
    SkillReq,
    StudentContext,
)
from silp.domain.recommendation.scorer import (
    ASSET_PREFERRED_SHARE,
    F_COURSE,
    F_NEED,
    skill_fit,
)
from silp.domain.text import to_persian_digits

MAX_POSITIVE_REASONS = 3
MAX_WARNING_REASONS = 2

# آستانه‌ها: زیر این‌ها دلیل ساخته نمی‌شود، چون «دلیل ضعیف» بدتر از
# نبودن دلیل است.
STRONG_INTEREST_LEVEL = 4
STRONG_GOAL_SCORE = 80.0
NEGLIGIBLE_CONTRIBUTION = 0.5

# §14.1 — متن سطوح مهارت، برای اینکه دلیل «سطح ۲ هستی» معنا داشته باشد.
SKILL_LEVEL_LABELS: dict[int, str] = {
    1: "نمی‌دانم",
    2: "آشنایی مقدماتی",
    3: "کار با کمک",
    4: "کار مستقل",
    5: "آموزش به دیگران",
}

TEACHABLE_NOTE = "در همین پروژه یاد می‌گیری"
NOT_TEACHABLE_NOTE = "بهتر است پیش از شروع تقویتش کنی"


def _skill_share(reqs: tuple[SkillReq, ...], req: SkillReq) -> float:
    total = sum(r.weight for r in reqs)
    return req.weight / total if total > 0 else 0.0


def _skill_reasons(ctx: StudentContext, match: MatchResult) -> list[Reason]:
    reqs = match.project.required_skills
    weight = match.weights.get(Component.SKILL, 0.0)
    if not reqs or weight <= 0:
        return []

    out: list[Reason] = []
    for req in reqs:
        fit = skill_fit(ctx, req)
        share = _skill_share(reqs, req)
        level = ctx.skill_level(req.skill_id)

        if fit >= 1.0 and req.skill_id in ctx.skills:
            # فقط مهارتی که دانشجو خودش اعلام کرده «نقطهٔ قوت» است؛
            # سطح فرضی ۱ هرگز دلیل مثبت نمی‌شود.
            out.append(
                Reason(
                    type=ReasonType.SKILL_STRONG,
                    polarity=Polarity.POSITIVE,
                    contribution=weight * share * MAX_SCORE,
                    text=(
                        f"{req.title_fa} را در سطح «{SKILL_LEVEL_LABELS[level]}» داری"
                        " و این پروژه به آن نیاز دارد"
                    ),
                )
            )
        elif fit < 1.0:
            note = TEACHABLE_NOTE if req.is_teachable else NOT_TEACHABLE_NOTE
            out.append(
                Reason(
                    type=ReasonType.SKILL_GAP,
                    polarity=Polarity.WARNING,
                    contribution=-weight * share * (1.0 - fit) * MAX_SCORE,
                    text=(
                        f"{req.title_fa} در سطح {to_persian_digits(req.min_level)} لازم است"
                        f" و تو در سطح {to_persian_digits(level)} هستی — {note}"
                    ),
                )
            )
    return out


def _asset_reasons(ctx: StudentContext, match: MatchResult) -> list[Reason]:
    reqs = match.project.required_assets
    weight = match.weights.get(Component.ASSET, 0.0)
    if not reqs or weight <= 0:
        return []

    owned = [r for r in reqs if r.asset_id in ctx.assets]
    preferred_missing = [r for r in reqs if not r.is_mandatory and r.asset_id not in ctx.assets]

    out: list[Reason] = []
    if owned:
        each = weight * match.breakdown[Component.ASSET] / len(owned)
        out += [
            Reason(
                type=ReasonType.ASSET_MATCH,
                polarity=Polarity.POSITIVE,
                contribution=each,
                text=f"{r.title_fa} داری و این پروژه به آن نیاز دارد",
            )
            for r in owned
        ]

    if preferred_missing:
        preferred_total = sum(1 for r in reqs if not r.is_mandatory)
        each = weight * ASSET_PREFERRED_SHARE * MAX_SCORE / max(1, preferred_total)
        out += [
            Reason(
                type=ReasonType.ASSET_MISSING,
                polarity=Polarity.WARNING,
                contribution=-each,
                text=f"{r.title_fa} به کار می‌آید ولی در نیمرخ تو ثبت نشده",
            )
            for r in preferred_missing
        ]

    return out


def _interest_reasons(ctx: StudentContext, match: MatchResult) -> list[Reason]:
    interests = match.project.interests
    weight = match.weights.get(Component.INTEREST, 0.0)
    if not interests or weight <= 0:
        return []

    out: list[Reason] = []
    for ref in interests:
        if ref.interest_id not in ctx.interests:
            continue
        level = ctx.interests[ref.interest_id]
        if level < STRONG_INTEREST_LEVEL:
            continue
        out.append(
            Reason(
                type=ReasonType.INTEREST_HIGH,
                polarity=Polarity.POSITIVE,
                contribution=weight * ((level - 1) / 4) * MAX_SCORE / len(interests),
                text=f"به {ref.title_fa} علاقهٔ زیادی نشان داده‌ای",
            )
        )
    return out


def _time_reason(ctx: StudentContext, match: MatchResult) -> list[Reason]:
    weight = match.weights.get(Component.TIME, 0.0)
    if weight <= 0:
        return []

    score = match.breakdown[Component.TIME]
    hours = ctx.effective_weekly_hours
    needed = match.project.time_commitment_hpw

    if score >= MAX_SCORE:
        return [
            Reason(
                type=ReasonType.TIME_FIT,
                polarity=Polarity.POSITIVE,
                contribution=weight * score,
                text=f"با {to_persian_digits(hours)} ساعت در هفتهٔ تو جور در می‌آید",
            )
        ]

    if needed is None:
        return []
    return [
        Reason(
            type=ReasonType.TIME_TIGHT,
            polarity=Polarity.WARNING,
            contribution=-weight * (MAX_SCORE - score),
            text=(
                f"به {to_persian_digits(needed)} ساعت در هفته نیاز دارد،"
                f" بیش از {to_persian_digits(hours)} ساعت تو"
            ),
        )
    ]


def _goal_reason(ctx: StudentContext, match: MatchResult) -> list[Reason]:
    weight = match.weights.get(Component.GOAL, 0.0)
    score = match.breakdown[Component.GOAL]
    if weight <= 0 or ctx.primary_goal is None or score < STRONG_GOAL_SCORE:
        return []

    return [
        Reason(
            type=ReasonType.GOAL_FIT,
            polarity=Polarity.POSITIVE,
            contribution=weight * score,
            text=f"با هدف تو ({GOAL_TITLE_FA[ctx.primary_goal]}) هم‌راستاست",
        )
    ]


def _factor_reasons(match: MatchResult) -> list[Reason]:
    """دلایلی که از ضرایب §8.9 می‌آیند، نه از زیرامتیازها.

    ضریب تشویقی روی **فاصلهٔ تا ۱۰۰** عمل می‌کند، پس سهمش هم همان است:
    چند واحد از آن فاصله را جبران کرده. اگر پایه ۹۵ باشد، اتصال به درس
    ۰.۷۵ واحد می‌دهد، نه ۱۴ واحد — و همین عدد کوچک، درست است.
    """
    out: list[Reason] = []
    headroom = MAX_SCORE - match.base_score

    if "f_course" in match.factors:
        title = match.project.offering_title_fa or "درسی که در آن ثبت‌نام کرده‌ای"
        out.append(
            Reason(
                type=ReasonType.COURSE_LINK,
                polarity=Polarity.POSITIVE,
                contribution=headroom * (F_COURSE - 1.0),
                text=f"به درس «{title}» که در آن ثبت‌نام کرده‌ای متصل است",
            )
        )

    if "f_need" in match.factors:
        short = match.project.members_short_of_min
        out.append(
            Reason(
                type=ReasonType.TEAM_NEED,
                polarity=Polarity.POSITIVE,
                contribution=headroom * (F_NEED - 1.0),
                text=f"این تیم هنوز {to_persian_digits(short)} نفر کم دارد",
            )
        )

    return out


def explain(ctx: StudentContext, match: MatchResult) -> tuple[Reason, ...]:
    """حداکثر ۳ دلیل مثبت و ۲ هشدار، مرتب بر اساس سهم — §8.10."""
    candidates = (
        _skill_reasons(ctx, match)
        + _asset_reasons(ctx, match)
        + _interest_reasons(ctx, match)
        + _time_reason(ctx, match)
        + _goal_reason(ctx, match)
        + _factor_reasons(match)
    )

    # دلیل ناچیز، اعتماد را کم می‌کند — «۰.۲ امتیاز از اکسل» چیزی نمی‌گوید.
    significant = [r for r in candidates if abs(r.contribution) >= NEGLIGIBLE_CONTRIBUTION]

    positive = sorted(
        (r for r in significant if r.polarity is Polarity.POSITIVE),
        key=lambda r: r.contribution,
        reverse=True,
    )[:MAX_POSITIVE_REASONS]
    warnings = sorted(
        (r for r in significant if r.polarity is Polarity.WARNING),
        key=lambda r: r.contribution,
    )[:MAX_WARNING_REASONS]

    # ترتیب نهایی: بزرگ‌ترین سهم اول، چه مثبت چه منفی.
    return tuple(sorted(positive + warnings, key=lambda r: abs(r.contribution), reverse=True))


def with_reasons(ctx: StudentContext, match: MatchResult) -> MatchResult:
    """همان نتیجه، با دلایل پرشده. `MatchResult` تغییرناپذیر است."""
    return replace(match, reasons=explain(ctx, match))


__all__ = [
    "MAX_POSITIVE_REASONS",
    "MAX_WARNING_REASONS",
    "SKILL_LEVEL_LABELS",
    "explain",
    "with_reasons",
]
