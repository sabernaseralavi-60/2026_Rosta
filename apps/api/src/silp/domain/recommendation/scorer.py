"""امتیازدهی تطابق دانشجو ← پروژه — PRD §8.2 تا §8.9.

**الزام §8.12:** همهٔ توابع این ماژول خالص‌اند. دیتاکلاس می‌گیرند و عدد
برمی‌گردانند؛ نه دیتابیس، نه ساعت سیستم، نه تصادف. هر چیزی که به زمان
نیاز دارد (§8.9 تازگی و فوریت) `now` را به‌عنوان آرگومان می‌گیرد.

این خلوص، شرط `test_score_is_deterministic_for_same_input` و آزمون ویژگی
§8.13 است.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from silp.domain.recommendation.schemas import (
    DEFAULT_TIME_COMMITMENT_HPW,
    MAX_SCORE,
    MIN_SCORE,
    AssetReq,
    Component,
    Goal,
    InterestRef,
    MatchResult,
    ProjectKind,
    ProjectSpec,
    SkillReq,
    StudentContext,
    Verdict,
    Weights,
    WorkStyle,
)

# ── §8.2 تطابق مهارت ───────────────────────────────────────────────────
# کمبود جزئی (۱ یا ۲ سطح) خطی جریمه می‌شود؛ کمبود جدی تقریباً حذف است.
MINOR_GAP_LIMIT = 2
MINOR_GAP_PENALTY = 0.25
SEVERE_GAP_BASE = 0.5
SEVERE_GAP_PENALTY = 0.15
VERIFIED_SKILL_BONUS = 1.25
TEACHABLE_SKILL_RELIEF = 0.20
# پروژه‌ای که مهارتی نخواسته، «خنثای مثبت» می‌گیرد، نه ۱۰۰: نبود نیاز،
# دلیل تطابق نیست.
NO_SKILL_REQ_SCORE = 70.0

# ── §8.3 تطابق امکانات ─────────────────────────────────────────────────
ASSET_BASE_SHARE = 0.6
ASSET_PREFERRED_SHARE = 0.4

# ── §8.4 تطابق علاقه ───────────────────────────────────────────────────
NO_INTEREST_SCORE = 60.0

# ── §8.5 تطابق زمان ────────────────────────────────────────────────────
TIME_COMFORT_MIN = 0.8
TIME_COMFORT_MAX = 2.0
TIME_SURPLUS_PENALTY_PER_UNIT = 10.0
TIME_SURPLUS_FLOOR = 60.0

# ── §8.6 تطابق سبک کار ─────────────────────────────────────────────────
# سطر: ترجیح دانشجو · ستون: سبک پروژه. `None` یعنی دانشجو گام ۴ را نزده.
STYLE_MATRIX: dict[WorkStyle | None, dict[WorkStyle, float]] = {
    WorkStyle.SOLO: {WorkStyle.SOLO: 100.0, WorkStyle.TEAM: 40.0, WorkStyle.EITHER: 90.0},
    WorkStyle.TEAM: {WorkStyle.SOLO: 40.0, WorkStyle.TEAM: 100.0, WorkStyle.EITHER: 90.0},
    WorkStyle.EITHER: {WorkStyle.SOLO: 85.0, WorkStyle.TEAM: 85.0, WorkStyle.EITHER: 100.0},
    None: {WorkStyle.SOLO: 75.0, WorkStyle.TEAM: 75.0, WorkStyle.EITHER: 80.0},
}

# ── §8.7 تطابق هدف ─────────────────────────────────────────────────────
# ستون `C_PROBLEM` عمداً برای بیشتر اهداف بالاست: حل مسئلهٔ واقعی هم‌زمان
# نمره، مهارت و رزومه می‌سازد و راهبرد محصول تشویق آن است.
GOAL_MATRIX: dict[Goal | None, dict[ProjectKind, float]] = {
    Goal.GRADE: {
        ProjectKind.A_VENTURE: 50.0,
        ProjectKind.B_RESEARCH: 70.0,
        ProjectKind.C_PROBLEM: 85.0,
        ProjectKind.D_PERSONAL: 40.0,
    },
    Goal.LEARNING: {
        ProjectKind.A_VENTURE: 75.0,
        ProjectKind.B_RESEARCH: 85.0,
        ProjectKind.C_PROBLEM: 90.0,
        ProjectKind.D_PERSONAL: 80.0,
    },
    Goal.PUBLICATION: {
        ProjectKind.A_VENTURE: 30.0,
        ProjectKind.B_RESEARCH: 100.0,
        ProjectKind.C_PROBLEM: 75.0,
        ProjectKind.D_PERSONAL: 40.0,
    },
    Goal.INCOME: {
        ProjectKind.A_VENTURE: 100.0,
        ProjectKind.B_RESEARCH: 30.0,
        ProjectKind.C_PROBLEM: 65.0,
        ProjectKind.D_PERSONAL: 50.0,
    },
    Goal.STARTUP: {
        ProjectKind.A_VENTURE: 100.0,
        ProjectKind.B_RESEARCH: 45.0,
        ProjectKind.C_PROBLEM: 80.0,
        ProjectKind.D_PERSONAL: 70.0,
    },
    Goal.EMPLOYMENT: {
        ProjectKind.A_VENTURE: 80.0,
        ProjectKind.B_RESEARCH: 70.0,
        ProjectKind.C_PROBLEM: 95.0,
        ProjectKind.D_PERSONAL: 60.0,
    },
    None: dict.fromkeys(ProjectKind, 70.0),
}

# ── §8.9 ضرایب تعدیل ───────────────────────────────────────────────────
RECENCY_WINDOW = timedelta(days=7)
URGENCY_WINDOW = timedelta(days=7)
CROWDED_RATIO = 3

F_RECENCY = 1.05
F_URGENCY = 1.08
F_NEED = 1.10
F_COURSE = 1.15
F_CROWDED = 0.90
F_DISMISSED = 0.20
F_HIDDEN = 0.0
F_INTERESTED = 1.10
F_APPLIED = 0.0

# §8.11 — پروژهٔ «کشش‌دار»: دشواری‌اش یک پله بالاتر از سطح دانشجوست.
STRETCH_MARGIN = 1.0


def _clamp(value: float, low: float = MIN_SCORE, high: float = MAX_SCORE) -> float:
    return max(low, min(high, value))


# ── §8.2 ───────────────────────────────────────────────────────────────
def skill_fit(ctx: StudentContext, req: SkillReq) -> float:
    """سازگاری دانشجو با یک مهارت لازم، بین ۰ و ۱.

    ترتیب اعمال دو پاداش اهمیت دارد و از سند پیروی می‌کند: ضریب تأیید
    **ضربی** است و پیش از تخفیف **جمعیِ** آموزش‌پذیری اعمال می‌شود.
    """
    gap = req.min_level - ctx.skill_level(req.skill_id)

    if gap <= 0:
        fit = 1.0
    elif gap <= MINOR_GAP_LIMIT:
        fit = 1.0 - MINOR_GAP_PENALTY * gap
    else:
        fit = max(0.0, SEVERE_GAP_BASE - SEVERE_GAP_PENALTY * gap)

    if req.skill_id in ctx.verified_skills:
        fit = min(1.0, fit * VERIFIED_SKILL_BONUS)
    if req.is_teachable:
        fit = min(1.0, fit + TEACHABLE_SKILL_RELIEF)

    return fit


def score_skill(ctx: StudentContext, reqs: Sequence[SkillReq]) -> float:
    """§8.2 — میانگین وزنی سازگاری مهارت‌ها."""
    if not reqs:
        return NO_SKILL_REQ_SCORE

    total_weight = sum(r.weight for r in reqs)
    if total_weight <= 0:  # پروژه‌ای با وزن‌های نامعتبر — مثل بی‌مهارت رفتار کن
        return NO_SKILL_REQ_SCORE

    weighted = sum(r.weight * skill_fit(ctx, r) for r in reqs)
    return _clamp(weighted / total_weight * MAX_SCORE)


# ── §8.3 ───────────────────────────────────────────────────────────────
def has_all_mandatory_assets(ctx: StudentContext, reqs: Sequence[AssetReq]) -> bool:
    """دروازهٔ امکانات. نداشتن یک مورد الزامی یعنی پروژه عملاً ناممکن است.

    **دروازه فقط وقتی باز می‌شود که دانشجو گام ۲ را پاسخ داده باشد.** پیش
    از آن، نبود ردیف یعنی «نمی‌دانیم»، نه «ندارد» — همان تفکیکی که §8.8
    برای مؤلفه‌های بی‌داده قائل است.

    بدون این قید، دانشجویی که تازه گام ۱ را زده هیچ پیشنهادی نمی‌گیرد
    (هر شش پروژهٔ §14.5 لپ‌تاپ را الزامی کرده‌اند) و «لحظهٔ طلایی» §01 که
    §5.3 بلافاصله پس از گام ۱ می‌خواهد، از بین می‌رود.
    """
    if not ctx.has_data_for(Component.ASSET):
        return True
    return all(r.asset_id in ctx.assets for r in reqs if r.is_mandatory)


def score_asset(ctx: StudentContext, reqs: Sequence[AssetReq]) -> float:
    """§8.3 — صفر یعنی حذف از فهرست پیشنهاد، نه «امتیاز کم»."""
    if not has_all_mandatory_assets(ctx, reqs):
        return MIN_SCORE

    preferred = [r for r in reqs if not r.is_mandatory]
    if not reqs:
        return MAX_SCORE
    if not preferred:
        # همهٔ الزامی‌ها را دارد و ترجیحی وجود ندارد.
        return MAX_SCORE

    owned = sum(1 for r in preferred if r.asset_id in ctx.assets)
    share = owned / len(preferred)
    return _clamp(MAX_SCORE * (ASSET_BASE_SHARE + ASSET_PREFERRED_SHARE * share))


# ── §8.4 ───────────────────────────────────────────────────────────────
def score_interest(ctx: StudentContext, interests: Sequence[InterestRef]) -> float:
    """§8.4 — تبدیل خطی: علاقهٔ ۱ ⇒ ۰، ۳ ⇒ ۵۰، ۵ ⇒ ۱۰۰."""
    if not interests:
        return NO_INTEREST_SCORE

    total = sum(ctx.interest_level(i.interest_id) - 1 for i in interests)
    return _clamp(total / (4 * len(interests)) * MAX_SCORE)


# ── §8.5 ───────────────────────────────────────────────────────────────
def score_time(ctx: StudentContext, project: ProjectSpec) -> float:
    """§8.5 — وقت کم جریمهٔ خطی دارد؛ وقت زیاد جریمهٔ خفیف و کف ۶۰."""
    needed = project.time_commitment_hpw or DEFAULT_TIME_COMMITMENT_HPW
    if needed <= 0:
        return MAX_SCORE

    ratio = ctx.effective_weekly_hours / needed

    if ratio < TIME_COMFORT_MIN:
        return _clamp(MAX_SCORE * (ratio / TIME_COMFORT_MIN))
    if ratio <= TIME_COMFORT_MAX:
        return MAX_SCORE
    surplus = ratio - TIME_COMFORT_MAX
    return _clamp(max(TIME_SURPLUS_FLOOR, MAX_SCORE - TIME_SURPLUS_PENALTY_PER_UNIT * surplus))


# ── §8.6 ───────────────────────────────────────────────────────────────
def score_style(ctx: StudentContext, project: ProjectSpec) -> float:
    return STYLE_MATRIX[ctx.work_style][project.work_style]


# ── §8.7 ───────────────────────────────────────────────────────────────
def score_goal(ctx: StudentContext, project: ProjectSpec) -> float:
    return GOAL_MATRIX[ctx.primary_goal][project.kind]


# ── §8.8 ───────────────────────────────────────────────────────────────
def effective_weights(ctx: StudentContext, weights: Weights) -> dict[Component, float]:
    """وزن مؤلفه‌های بی‌داده صفر و بقیه بازنرمال می‌شود.

    بدون این کار، دانشجویی که فقط گام ۱ را پر کرده هرگز از ~۳۵ بالاتر
    نمی‌رود و «لحظهٔ طلایی» §01 از دست می‌رود.
    """
    configured = weights.as_dict()
    active = {k: w for k, w in configured.items() if w > 0 and ctx.has_data_for(k)}

    total = sum(active.values())
    if total <= 0:
        # نیمرخ کاملاً خالی: همهٔ مؤلفه‌ها با وزن اصلی، روی مقادیر پیش‌فرض.
        fallback_total = sum(configured.values())
        return {k: w / fallback_total for k, w in configured.items()}

    return {k: w / total for k, w in active.items()}


def combine(breakdown: dict[Component, float], weights: dict[Component, float]) -> float:
    return _clamp(sum(weights.get(k, 0.0) * v for k, v in breakdown.items()))


# ── §8.9 ───────────────────────────────────────────────────────────────
def adjustment_factors(
    ctx: StudentContext, project: ProjectSpec, *, now: datetime
) -> dict[str, float]:
    """ضرایب تعدیل. کلیدها همان نام سند‌اند تا در لاگ قابل ردیابی باشند."""
    factors: dict[str, float] = {}

    if project.published_at is not None and now - project.published_at <= RECENCY_WINDOW:
        factors["f_recency"] = F_RECENCY

    if project.applications_close_at is not None:
        remaining = project.applications_close_at - now
        if timedelta(0) < remaining <= URGENCY_WINDOW:
            factors["f_urgency"] = F_URGENCY

    if project.members_short_of_min > 0:
        factors["f_need"] = F_NEED

    if project.offering_id is not None and project.offering_id in ctx.enrolled_offerings:
        factors["f_course"] = F_COURSE

    if project.pending_applications > CROWDED_RATIO * max(1, project.open_seats):
        factors["f_crowded"] = F_CROWDED

    match ctx.feedback.get(project.id):
        case Verdict.NOT_RELEVANT:
            factors["f_dismissed"] = F_DISMISSED
        case Verdict.DISMISSED:
            factors["f_hidden"] = F_HIDDEN
        case Verdict.INTERESTED:
            factors["f_interested"] = F_INTERESTED
        case _:
            pass

    if project.id in ctx.applied_project_ids:
        factors["f_applied"] = F_APPLIED

    return factors


def apply_factors(base: float, factors: dict[str, float]) -> float:
    """اعمال ضرایب §8.9 — جریمه ضربی، تشویق روی فاصلهٔ باقی‌مانده.

    سند `final = min(100, base × Π f)` را می‌گفت. اجرای واقعی نشان داد آن
    فرمول اطلاعات را از بین می‌برد: امتیاز پایهٔ پروژه‌های خوب بین ۹۰ تا
    ۱۰۰ است و حاصل‌ضرب ضرایب تشویقی تا ۱.۴ می‌رسد، پس `min` تقریباً همیشه
    فعال می‌شود و سه پیشنهاد برتر هر سه «۱۰۰٪» نشان می‌دهند. دانشجو
    نمی‌فهمد کدام بهتر است و `MatchRing` سه حلقهٔ یکسان می‌شود.

    فرمول جایگزین:

        اگر ضریبی صفر باشد (پنهان‌شده، درخواست‌داده)  ⇒  ۰
        جریمه‌ها (f < 1) ضربی می‌مانند:  s = base × Π f⁻
        تشویق‌ها روی هِدروم می‌نشینند:   final = s + (100 − s) × (Π f⁺ − 1)

    سه ویژگی که این فرمول را درست می‌کند:

    ۱. **هرگز از ۱۰۰ رد نمی‌شود**، پس بریدنی در کار نیست و تفاوت‌ها
       نگه داشته می‌شوند. پروژهٔ ۸۹ و پروژهٔ ۹۵ بعد از تشویق یکسان هم،
       همچنان از هم قابل تفکیک‌اند.
    ۲. **ترتیب را حفظ می‌کند.** برای دو پایهٔ b₁ > b₂ با ضریب یکسان F،
       اختلاف نهایی (b₁−b₂)(2−F) است؛ چون بیشینهٔ F اینجا ۱.۶ است و
       کمتر از ۲، علامت اختلاف عوض نمی‌شود.
    ۳. **معنای قابل توضیح دارد:** «اتصال به درس، ۱۵٪ از فاصلهٔ تو تا
       تطابق کامل را جبران می‌کند» — که با §8.10 سازگار است.

    جریمه‌ها عمداً ضربی مانده‌اند: «این به من نمی‌خورد» باید امتیاز را
    واقعاً پایین بیاورد، نه اینکه به سقف نزدیکش کند.

    تفصیل و گزینه‌های رد شده در docs/adr/0005.
    """
    if any(value == 0 for value in factors.values()):
        return MIN_SCORE

    penalty = 1.0
    boost = 1.0
    for value in factors.values():
        if value < 1.0:
            penalty *= value
        else:
            boost *= value

    scored = _clamp(base * penalty)
    headroom_share = min(1.0, boost - 1.0)
    return _clamp(scored + (MAX_SCORE - scored) * headroom_share)


# ── هماهنگی ────────────────────────────────────────────────────────────
def score_project(
    ctx: StudentContext,
    project: ProjectSpec,
    weights: Weights | None = None,
    *,
    now: datetime,
) -> MatchResult:
    """امتیاز نهایی یک پروژه برای یک دانشجو — §8.8 و §8.9.

    دلایل اینجا ساخته نمی‌شوند؛ `explainer.explain()` روی همین خروجی کار
    می‌کند. جدا نگه‌داشتنشان یعنی تست امتیاز به تغییر متن فارسی حساس نیست.
    """
    weights = weights or Weights()

    breakdown: dict[Component, float] = {
        Component.SKILL: score_skill(ctx, project.required_skills),
        Component.ASSET: score_asset(ctx, project.required_assets),
        Component.INTEREST: score_interest(ctx, project.interests),
        Component.TIME: score_time(ctx, project),
        Component.STYLE: score_style(ctx, project),
        Component.GOAL: score_goal(ctx, project),
    }

    effective = effective_weights(ctx, weights)
    base = combine(breakdown, effective)
    factors = adjustment_factors(ctx, project, now=now)
    final = apply_factors(base, factors)

    missing_mandatory = not has_all_mandatory_assets(ctx, project.required_assets)
    hidden = ctx.feedback.get(project.id) is Verdict.DISMISSED
    applied = project.id in ctx.applied_project_ids

    exclusion: str | None = None
    if missing_mandatory:
        exclusion = "MISSING_MANDATORY_ASSET"
    elif applied:
        exclusion = "ALREADY_APPLIED"
    elif hidden:
        exclusion = "DISMISSED_BY_USER"

    return MatchResult(
        project=project,
        score=final,
        base_score=base,
        breakdown=breakdown,
        weights=effective,
        factors=factors,
        is_excluded=exclusion is not None,
        exclusion_reason=exclusion,
        is_stretch=project.difficulty >= ctx.average_skill_level + STRETCH_MARGIN,
    )


def profile_completeness(ctx: StudentContext) -> float:
    """نسبت گام‌های تکمیل‌شده — §5.7 `profile_completeness`."""
    total_steps = 4
    return _clamp(ctx.completed_steps / total_steps, 0.0, 1.0)


__all__ = [
    "GOAL_MATRIX",
    "STYLE_MATRIX",
    "adjustment_factors",
    "apply_factors",
    "combine",
    "effective_weights",
    "has_all_mandatory_assets",
    "profile_completeness",
    "score_asset",
    "score_goal",
    "score_interest",
    "score_project",
    "score_skill",
    "score_style",
    "score_time",
    "skill_fit",
]
