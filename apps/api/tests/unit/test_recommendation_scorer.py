"""تست‌های الزامی موتور توصیه‌گر — PRD §8.13.

هر تستی که سند اسمش را برده، اینجا با همان نام هست. بدون دیتابیس اجرا
می‌شود، چون `scorer` توابع خالص دارد (§8.12).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from silp.domain.recommendation.diversity import diversify, ensure_stretch
from silp.domain.recommendation.explainer import explain
from silp.domain.recommendation.schemas import (
    MAX_SCORE,
    MIN_SCORE,
    AssetReq,
    Component,
    Goal,
    InterestRef,
    Polarity,
    ProjectKind,
    ProjectSpec,
    SkillReq,
    StudentContext,
    Verdict,
    Weights,
    WorkStyle,
)
from silp.domain.recommendation.scorer import (
    apply_factors,
    effective_weights,
    score_asset,
    score_goal,
    score_interest,
    score_project,
    score_skill,
    score_style,
    score_time,
    skill_fit,
)

NOW = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

PYTHON = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
GIS = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
WRITING = uuid.UUID("00000000-0000-0000-0000-0000000000a3")

MOTORCYCLE = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
LAPTOP = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
CAR = uuid.UUID("00000000-0000-0000-0000-0000000000b3")

SALES = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
RESEARCH = uuid.UUID("00000000-0000-0000-0000-0000000000c2")

USER = uuid.UUID("00000000-0000-0000-0000-0000000000ff")


def student(**overrides: object) -> StudentContext:
    """دانشجوی کامل: هر چهار گام پر، برای اینکه وزن‌ها بازنرمال نشوند."""
    base: dict[str, object] = {
        "user_id": USER,
        "skills": {PYTHON: 4, GIS: 2, WRITING: 1},
        "assets": frozenset({LAPTOP, MOTORCYCLE}),
        "interests": {SALES: 5, RESEARCH: 2},
        "weekly_hours": 10,
        "work_style": WorkStyle.TEAM,
        "primary_goal": Goal.INCOME,
        "completed_steps": 4,
    }
    base.update(overrides)
    return StudentContext(**base)  # type: ignore[arg-type]


def project(**overrides: object) -> ProjectSpec:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "title_fa": "پروژهٔ نمونه",
        "kind": ProjectKind.A_VENTURE,
        "difficulty": 2,
        "work_style": WorkStyle.TEAM,
        "time_commitment_hpw": 8,
        "team_size_min": 2,
        "team_size_max": 5,
        "active_members": 2,
    }
    base.update(overrides)
    return ProjectSpec(**base)  # type: ignore[arg-type]


# ── §8.2 مهارت ─────────────────────────────────────────────────────────
def test_skill_example_from_spec_matches() -> None:
    """مثال عددی §8.2 باید دقیقاً ۸۲.۵ بدهد.

    این تست، سند را می‌پاید: اگر کسی ضرایب را عوض کند، اینجا می‌شکند.
    """
    ctx = student(skills={PYTHON: 4, GIS: 2, WRITING: 1})
    reqs = [
        SkillReq(PYTHON, "پایتون", min_level=3, weight=3),
        SkillReq(GIS, "GIS", min_level=3, weight=2, is_teachable=True),
        SkillReq(WRITING, "نگارش", min_level=4, weight=1),
    ]
    assert score_skill(ctx, reqs) == pytest.approx(82.5)


def test_teachable_skill_softens_gap() -> None:
    ctx = student(skills={GIS: 2})
    hard = SkillReq(GIS, "GIS", min_level=4, weight=1)
    soft = SkillReq(GIS, "GIS", min_level=4, weight=1, is_teachable=True)
    assert skill_fit(ctx, soft) > skill_fit(ctx, hard)


def test_verified_skill_gets_bonus() -> None:
    req = SkillReq(GIS, "GIS", min_level=3, weight=1)
    plain = student(skills={GIS: 2})
    verified = student(skills={GIS: 2}, verified_skills=frozenset({GIS}))
    assert skill_fit(verified, req) > skill_fit(plain, req)


def test_project_without_skill_requirements_is_neutral_positive() -> None:
    assert score_skill(student(), []) == pytest.approx(70.0)


def test_unanswered_skill_is_treated_as_level_one() -> None:
    """§8.2 — مهارت پاسخ‌نداده بدترین حالت است، نه خنثی."""
    unknown = uuid.uuid4()
    req = SkillReq(unknown, "مهارت ناشناخته", min_level=3, weight=1)
    assert skill_fit(student(), req) == skill_fit(student(skills={unknown: 1}), req)


# ── §8.3 امکانات ───────────────────────────────────────────────────────
def test_missing_mandatory_asset_excludes_project() -> None:
    """دروازهٔ §8.3 — بدون خودرو، پروژهٔ توزیع اصلاً پیشنهاد نمی‌شود."""
    ctx = student(assets=frozenset({LAPTOP}))
    spec = project(required_assets=(AssetReq(CAR, "خودرو", is_mandatory=True),))

    assert score_asset(ctx, spec.required_assets) == MIN_SCORE
    result = score_project(ctx, spec, now=NOW)
    assert result.is_excluded
    assert result.exclusion_reason == "MISSING_MANDATORY_ASSET"


def test_preferred_assets_scale_between_60_and_100() -> None:
    reqs = [
        AssetReq(LAPTOP, "لپ‌تاپ", is_mandatory=True),
        AssetReq(MOTORCYCLE, "موتور"),
        AssetReq(CAR, "خودرو"),
    ]
    none_owned = student(assets=frozenset({LAPTOP}))
    half_owned = student(assets=frozenset({LAPTOP, MOTORCYCLE}))
    all_owned = student(assets=frozenset({LAPTOP, MOTORCYCLE, CAR}))

    assert score_asset(none_owned, reqs) == pytest.approx(60.0)
    assert score_asset(half_owned, reqs) == pytest.approx(80.0)
    assert score_asset(all_owned, reqs) == pytest.approx(100.0)


def test_project_without_asset_requirements_scores_full() -> None:
    assert score_asset(student(assets=frozenset()), []) == MAX_SCORE


# ── §8.4 علاقه ─────────────────────────────────────────────────────────
def test_interest_is_linear_from_one_to_five() -> None:
    refs = [InterestRef(SALES, "فروش")]
    assert score_interest(student(interests={SALES: 1}), refs) == pytest.approx(0.0)
    assert score_interest(student(interests={SALES: 3}), refs) == pytest.approx(50.0)
    assert score_interest(student(interests={SALES: 5}), refs) == pytest.approx(100.0)


def test_unanswered_interest_is_neutral() -> None:
    """پاسخ‌نداده = سطح ۳ = ۵۰. بی‌علاقگی ثابت نشده است."""
    assert score_interest(student(interests={}), [InterestRef(SALES, "فروش")]) == pytest.approx(
        50.0
    )


def test_project_without_interests_scores_sixty() -> None:
    assert score_interest(student(), []) == pytest.approx(60.0)


# ── §8.5 زمان ──────────────────────────────────────────────────────────
def test_time_comfort_band_scores_full() -> None:
    ctx = student(weekly_hours=10)
    assert score_time(ctx, project(time_commitment_hpw=10)) == MAX_SCORE
    assert score_time(ctx, project(time_commitment_hpw=12)) == MAX_SCORE  # ratio 0.83
    assert score_time(ctx, project(time_commitment_hpw=5)) == MAX_SCORE  # ratio 2.0


def test_too_little_time_is_penalized_linearly() -> None:
    ctx = student(weekly_hours=4)
    # ratio = 4/10 = 0.4 ⇒ 100 × (0.4 / 0.8) = 50
    assert score_time(ctx, project(time_commitment_hpw=10)) == pytest.approx(50.0)


def test_surplus_time_never_drops_below_sixty() -> None:
    ctx = student(weekly_hours=80)
    assert score_time(ctx, project(time_commitment_hpw=1)) >= 60.0


# ── §8.6 و §8.7 ────────────────────────────────────────────────────────
def test_style_matrix_penalizes_opposite_preference() -> None:
    solo = student(work_style=WorkStyle.SOLO)
    assert score_style(solo, project(work_style=WorkStyle.TEAM)) == pytest.approx(40.0)
    assert score_style(solo, project(work_style=WorkStyle.SOLO)) == pytest.approx(100.0)


def test_unknown_style_gets_moderate_score() -> None:
    assert score_style(student(work_style=None), project(work_style=WorkStyle.TEAM)) == 75.0


def test_goal_matrix_follows_spec() -> None:
    income = student(primary_goal=Goal.INCOME)
    assert score_goal(income, project(kind=ProjectKind.A_VENTURE)) == 100.0
    assert score_goal(income, project(kind=ProjectKind.B_RESEARCH)) == 30.0

    publication = student(primary_goal=Goal.PUBLICATION)
    assert score_goal(publication, project(kind=ProjectKind.B_RESEARCH)) == 100.0


def test_problem_solving_is_strong_for_every_goal() -> None:
    """§8.7 — راهبرد محصول: نوع C برای همهٔ اهداف امتیاز بالایی دارد."""
    for goal in Goal:
        ctx = student(primary_goal=goal)
        assert score_goal(ctx, project(kind=ProjectKind.C_PROBLEM)) >= 65.0


# ── §8.8 بازنرمال‌سازی وزن ──────────────────────────────────────────────
def test_weights_renormalize_for_incomplete_profile() -> None:
    """دانشجویی که فقط گام ۱ را زده، نباید امتیاز ۳۰ بگیرد."""
    partial = StudentContext(user_id=USER, skills={PYTHON: 4}, completed_steps=1)
    weights = effective_weights(partial, Weights())

    assert set(weights) == {Component.SKILL}
    assert sum(weights.values()) == pytest.approx(1.0)


def test_empty_profile_returns_reasonable_scores() -> None:
    """نیمرخ کاملاً خالی هم باید عدد معنادار بدهد، نه صفر."""
    empty = StudentContext(user_id=USER)
    result = score_project(empty, project(), now=NOW)
    assert MIN_SCORE < result.score <= MAX_SCORE


def test_partial_profile_scores_higher_than_naive_zero_weighting() -> None:
    strong = StudentContext(user_id=USER, skills={PYTHON: 5}, completed_steps=1)
    spec = project(required_skills=(SkillReq(PYTHON, "پایتون", min_level=3, weight=3),))
    # فقط مهارت داده دارد و مهارتش عالی است ⇒ امتیاز باید نزدیک ۱۰۰ باشد.
    assert score_project(strong, spec, now=NOW).base_score == pytest.approx(100.0)


# ── §8.9 ضرایب ─────────────────────────────────────────────────────────
def test_dismissed_project_ranks_last() -> None:
    spec = project()
    plain = student()
    dismissive = student(feedback={spec.id: Verdict.NOT_RELEVANT})
    assert (
        score_project(dismissive, spec, now=NOW).score < score_project(plain, spec, now=NOW).score
    )


def test_hidden_project_is_excluded() -> None:
    spec = project()
    ctx = student(feedback={spec.id: Verdict.DISMISSED})
    result = score_project(ctx, spec, now=NOW)
    assert result.is_excluded
    assert result.exclusion_reason == "DISMISSED_BY_USER"


def test_already_applied_project_is_excluded() -> None:
    spec = project()
    ctx = student(applied_project_ids=frozenset({spec.id}))
    result = score_project(ctx, spec, now=NOW)
    assert result.is_excluded
    assert result.exclusion_reason == "ALREADY_APPLIED"


def test_interested_feedback_boosts_score() -> None:
    spec = project()
    plain = student()
    interested = student(feedback={spec.id: Verdict.INTERESTED})
    assert (
        score_project(interested, spec, now=NOW).score > score_project(plain, spec, now=NOW).score
    )


def test_urgency_factor_applies_only_inside_window() -> None:
    soon = project(applications_close_at=NOW + timedelta(days=3))
    later = project(applications_close_at=NOW + timedelta(days=30))
    assert "f_urgency" in score_project(student(), soon, now=NOW).factors
    assert "f_urgency" not in score_project(student(), later, now=NOW).factors


def test_team_need_factor_when_below_minimum() -> None:
    short = project(team_size_min=3, team_size_max=5, active_members=1)
    full = project(team_size_min=3, team_size_max=5, active_members=3)
    assert "f_need" in score_project(student(), short, now=NOW).factors
    assert "f_need" not in score_project(student(), full, now=NOW).factors


def test_boosts_never_reach_the_ceiling() -> None:
    """§8.9 — ضریب تشویقی روی هِدروم می‌نشیند، پس ۱۰۰ لمس نمی‌شود.

    این همان اشکالی است که فرمول ضربی سند داشت: سه پیشنهاد برتر هر سه
    «۱۰۰٪» می‌شدند و `MatchRing` بی‌معنا می‌شد.
    """
    assert apply_factors(90.0, {"f_need": 1.10, "f_recency": 1.05}) < MAX_SCORE
    assert apply_factors(99.0, {"f_course": 1.15}) < MAX_SCORE


def test_boosts_preserve_the_ordering_of_base_scores() -> None:
    """دو پروژه با ضریب یکسان نباید جایشان عوض شود یا یکی شوند."""
    factors = {"f_need": 1.10, "f_recency": 1.05, "f_course": 1.15}
    weaker = apply_factors(89.0, factors)
    stronger = apply_factors(95.0, factors)

    assert weaker < stronger
    assert stronger - weaker > 1.0, "تفاوت نباید تا حد نادیدنی فشرده شود"


def test_penalties_stay_multiplicative() -> None:
    """«این به من نمی‌خورد» باید واقعاً پایین بیاورد، نه به سقف نزدیک کند."""
    assert apply_factors(80.0, {"f_dismissed": 0.20}) == pytest.approx(16.0)
    assert apply_factors(80.0, {"f_crowded": 0.90}) == pytest.approx(72.0)


def test_a_zero_factor_zeroes_the_score() -> None:
    """پنهان‌شده و درخواست‌داده‌شده، حتی با تشویق هم صفر می‌مانند."""
    assert apply_factors(95.0, {"f_hidden": 0.0, "f_need": 1.10}) == MIN_SCORE
    assert apply_factors(95.0, {"f_applied": 0.0}) == MIN_SCORE


def test_factors_never_push_past_one_hundred() -> None:
    """حتی با همهٔ ضرایب تشویقی هم‌زمان."""
    everything = {
        "f_recency": 1.05,
        "f_urgency": 1.08,
        "f_need": 1.10,
        "f_course": 1.15,
        "f_interested": 1.10,
    }
    assert apply_factors(99.9, everything) <= MAX_SCORE


def test_crowded_project_is_penalized() -> None:
    crowded = project(team_size_max=5, active_members=4, pending_applications=10)
    assert score_project(student(), crowded, now=NOW).factors.get("f_crowded") == pytest.approx(
        0.90
    )


# ── §8.10 دلایل ────────────────────────────────────────────────────────
def test_reasons_are_sorted_by_contribution() -> None:
    ctx = student()
    spec = project(
        required_skills=(
            SkillReq(PYTHON, "پایتون", min_level=3, weight=3),
            SkillReq(WRITING, "نگارش علمی", min_level=4, weight=1),
        ),
        required_assets=(AssetReq(MOTORCYCLE, "موتورسیکلت", is_mandatory=True),),
        interests=(InterestRef(SALES, "فروش"),),
    )
    reasons = explain(ctx, score_project(ctx, spec, now=NOW))

    contributions = [abs(r.contribution) for r in reasons]
    assert contributions == sorted(contributions, reverse=True)


def test_reason_counts_are_capped() -> None:
    """حداکثر ۳ مثبت و ۲ هشدار — §8.10."""
    ctx = student(
        skills={PYTHON: 5, GIS: 5, WRITING: 5}, assets=frozenset({LAPTOP, MOTORCYCLE, CAR})
    )
    spec = project(
        required_skills=tuple(
            SkillReq(s, f"مهارت {i}", min_level=2, weight=1)
            for i, s in enumerate((PYTHON, GIS, WRITING))
        ),
        required_assets=(
            AssetReq(LAPTOP, "لپ‌تاپ"),
            AssetReq(MOTORCYCLE, "موتور"),
            AssetReq(CAR, "خودرو"),
        ),
        interests=(InterestRef(SALES, "فروش"),),
    )
    reasons = explain(ctx, score_project(ctx, spec, now=NOW))

    assert sum(1 for r in reasons if r.polarity is Polarity.POSITIVE) <= 3
    assert sum(1 for r in reasons if r.polarity is Polarity.WARNING) <= 2


def test_reason_text_is_persian_and_non_empty() -> None:
    ctx = student()
    spec = project(
        required_skills=(SkillReq(WRITING, "نگارش علمی", min_level=4, weight=2),),
        interests=(InterestRef(SALES, "فروش"),),
    )
    reasons = explain(ctx, score_project(ctx, spec, now=NOW))

    assert reasons
    for reason in reasons:
        assert reason.text.strip()
        # متن باید فارسی باشد، نه کلید ترجمه.
        assert any("؀" <= ch <= "ۿ" for ch in reason.text)


def test_unanswered_skill_never_becomes_a_strength() -> None:
    """سطح فرضی ۱ نباید دلیل مثبت «این مهارت را داری» بسازد."""
    unknown = uuid.uuid4()
    ctx = student(skills={PYTHON: 4})
    spec = project(required_skills=(SkillReq(unknown, "مهارت ناشناخته", min_level=1, weight=1),))
    reasons = explain(ctx, score_project(ctx, spec, now=NOW))

    assert all(r.type.value != "SKILL_STRONG" for r in reasons)


# ── §8.11 تنوع ─────────────────────────────────────────────────────────
def _ranked(kinds: list[ProjectKind]) -> list:
    ctx = student()
    return [score_project(ctx, project(kind=k), now=NOW) for k in kinds]


def test_diversity_caps_single_kind_at_four() -> None:
    """سهمیهٔ §8.11 وقتی تنوع کافی در استخر هست."""
    ranked = _ranked(
        [ProjectKind.B_RESEARCH] * 8 + [ProjectKind.A_VENTURE] * 4 + [ProjectKind.C_PROBLEM] * 4
    )
    chosen = diversify(ranked, k=10)

    assert sum(1 for m in chosen if m.kind is ProjectKind.B_RESEARCH) == 4
    assert len(chosen) == 10


def test_quota_yields_to_filling_the_result_set() -> None:
    """§8.11 — «اگر به k نرسیدیم، از باقی‌مانده پر کن».

    سهمیه نرم است: ده نتیجه از یک نوع، بهتر از هشت نتیجه و دو جای خالی
    است. سند هر دو قاعده را دارد و این یکی برنده است.
    """
    ranked = _ranked([ProjectKind.B_RESEARCH] * 8 + [ProjectKind.A_VENTURE] * 4)
    chosen = diversify(ranked, k=10)

    assert len(chosen) == 10
    assert sum(1 for m in chosen if m.kind is ProjectKind.B_RESEARCH) > 4


def test_diversity_keeps_top_result_first() -> None:
    ranked = _ranked([ProjectKind.A_VENTURE] * 6)
    chosen = diversify(ranked, k=6)
    assert chosen[0] is ranked[0]


def test_diversity_fills_to_k_when_quota_runs_out() -> None:
    ranked = _ranked([ProjectKind.A_VENTURE] * 10)
    assert len(diversify(ranked, k=10)) == 10


def test_ensure_stretch_adds_a_challenging_project() -> None:
    ctx = student(skills={PYTHON: 2, GIS: 2, WRITING: 2})  # میانگین ۲
    easy = [score_project(ctx, project(difficulty=1), now=NOW) for _ in range(3)]
    hard = score_project(ctx, project(difficulty=5), now=NOW)

    assert not any(m.is_stretch for m in easy)
    assert hard.is_stretch

    result = ensure_stretch(easy, [*easy, hard], k=3)
    assert any(m.is_stretch for m in result)


# ── قطعیت و کران ───────────────────────────────────────────────────────
def test_score_is_deterministic_for_same_input() -> None:
    ctx = student()
    spec = project(
        required_skills=(SkillReq(PYTHON, "پایتون", min_level=3, weight=2),),
        required_assets=(AssetReq(LAPTOP, "لپ‌تاپ", is_mandatory=True),),
        interests=(InterestRef(SALES, "فروش"),),
    )
    first = score_project(ctx, spec, now=NOW)
    second = score_project(ctx, spec, now=NOW)

    assert first.score == second.score
    assert first.breakdown == second.breakdown
    assert [r.text for r in explain(ctx, first)] == [r.text for r in explain(ctx, second)]


# ── آزمون ویژگی §8.13 ──────────────────────────────────────────────────
levels = st.integers(min_value=1, max_value=5)
skill_ids = st.sampled_from([PYTHON, GIS, WRITING])
asset_ids = st.sampled_from([LAPTOP, MOTORCYCLE, CAR])
interest_ids = st.sampled_from([SALES, RESEARCH])

contexts = st.builds(
    StudentContext,
    user_id=st.just(USER),
    skills=st.dictionaries(skill_ids, levels, max_size=3),
    assets=st.frozensets(asset_ids, max_size=3),
    interests=st.dictionaries(interest_ids, levels, max_size=2),
    weekly_hours=st.one_of(st.none(), st.integers(min_value=0, max_value=80)),
    work_style=st.one_of(st.none(), st.sampled_from(list(WorkStyle))),
    primary_goal=st.one_of(st.none(), st.sampled_from(list(Goal))),
    completed_steps=st.integers(min_value=0, max_value=4),
)

specs = st.builds(
    ProjectSpec,
    id=st.just(uuid.UUID("00000000-0000-0000-0000-00000000dddd")),
    title_fa=st.just("پروژه"),
    kind=st.sampled_from(list(ProjectKind)),
    difficulty=st.integers(min_value=1, max_value=5),
    work_style=st.sampled_from(list(WorkStyle)),
    time_commitment_hpw=st.one_of(st.none(), st.integers(min_value=1, max_value=60)),
    required_skills=st.lists(
        st.builds(
            SkillReq,
            skill_id=skill_ids,
            title_fa=st.just("مهارت"),
            min_level=levels,
            weight=st.integers(min_value=1, max_value=3),
            is_teachable=st.booleans(),
        ),
        max_size=3,
        unique_by=lambda r: r.skill_id,
    ).map(tuple),
    required_assets=st.lists(
        st.builds(
            AssetReq,
            asset_id=asset_ids,
            title_fa=st.just("امکانات"),
            is_mandatory=st.booleans(),
        ),
        max_size=3,
        unique_by=lambda r: r.asset_id,
    ).map(tuple),
    interests=st.lists(
        st.builds(InterestRef, interest_id=interest_ids, title_fa=st.just("حوزه")),
        max_size=2,
        unique_by=lambda r: r.interest_id,
    ).map(tuple),
)


@given(ctx=contexts, spec=specs)
@settings(max_examples=250, deadline=None)
def test_score_stays_within_0_100(ctx: StudentContext, spec: ProjectSpec) -> None:
    result = score_project(ctx, spec, now=NOW)
    assert MIN_SCORE <= result.score <= MAX_SCORE
    assert MIN_SCORE <= result.base_score <= MAX_SCORE
    for value in result.breakdown.values():
        assert MIN_SCORE <= value <= MAX_SCORE


@given(ctx=contexts, spec=specs)
@settings(max_examples=250, deadline=None)
def test_raising_a_skill_never_lowers_the_score(ctx: StudentContext, spec: ProjectSpec) -> None:
    """یکنواختی §8.13 — تقویت یک مهارت هرگز امتیاز را کم نمی‌کند.

    مقایسه روی `base_score` انجام می‌شود، نه `score`: ضرایب §8.9 به مهارت
    ربطی ندارند و مقایسه را نویزی می‌کنند.
    """
    if not spec.required_skills:
        return
    target = spec.required_skills[0].skill_id

    before = score_project(ctx, spec, now=NOW).base_score
    stronger = StudentContext(
        user_id=ctx.user_id,
        skills={**ctx.skills, target: 5},
        verified_skills=ctx.verified_skills,
        assets=ctx.assets,
        interests=ctx.interests,
        weekly_hours=ctx.weekly_hours,
        work_style=ctx.work_style,
        primary_goal=ctx.primary_goal,
        completed_steps=max(ctx.completed_steps, 1),
    )
    after = score_project(stronger, spec, now=NOW).base_score

    # وقتی نیمرخ قبلی هیچ مهارتی نداشت، افزودن مهارت وزن‌ها را هم عوض
    # می‌کند (§8.8) و مقایسه بی‌معنا می‌شود.
    if ctx.skills:
        assert after >= before - 1e-9
