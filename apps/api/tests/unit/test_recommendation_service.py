"""بخش‌های بدون I/O سرویس توصیه‌گر — §8.11 و §8.12.

`rank`، کدگذاری کش، و ساخت کوئری نامزد بدون دیتابیس قابل آزمایش‌اند:
اولی منطق خالص است، دومی فقط JSON، و سومی فقط SQL تولید می‌کند.
مسیرهای واقعی دیتابیس در `tests/integration/test_recommendation_flow.py`
آزمایش می‌شوند.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from silp.domain.recommendation import service
from silp.domain.recommendation.schemas import (
    AssetReq,
    Goal,
    InterestRef,
    ProjectKind,
    ProjectSpec,
    SkillReq,
    StudentContext,
    Verdict,
    WorkStyle,
)
from silp.domain.text import join_fa, to_persian_digits

NOW = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
USER = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
SKILL = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ASSET = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
INTEREST = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


def ctx(**overrides: object) -> StudentContext:
    base: dict[str, object] = {
        "user_id": USER,
        "skills": {SKILL: 4},
        "assets": frozenset({ASSET}),
        "interests": {INTEREST: 5},
        "weekly_hours": 10,
        "work_style": WorkStyle.TEAM,
        "primary_goal": Goal.INCOME,
        "completed_steps": 4,
    }
    base.update(overrides)
    return StudentContext(**base)  # type: ignore[arg-type]


def spec(**overrides: object) -> ProjectSpec:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "title_fa": "پروژهٔ نمونه",
        "kind": ProjectKind.A_VENTURE,
        "difficulty": 2,
        "work_style": WorkStyle.TEAM,
        "time_commitment_hpw": 8,
        "team_size_min": 1,
        "team_size_max": 5,
        "active_members": 1,
        "required_skills": (SkillReq(SKILL, "پایتون", min_level=3, weight=2),),
        "required_assets": (AssetReq(ASSET, "لپ‌تاپ", is_mandatory=True),),
        "interests": (InterestRef(INTEREST, "فروش"),),
        # بدون تاریخ انتشار و بدون کمبود عضو: هیچ ضریب §8.9 فعال نیست، تا
        # تست‌ها امتیاز پایه را ببینند نه سقف ۱۰۰ را.
        "published_at": None,
    }
    base.update(overrides)
    return ProjectSpec(**base)  # type: ignore[arg-type]


# ── rank ───────────────────────────────────────────────────────────────
def test_rank_sorts_by_score_descending() -> None:
    student = ctx()
    weak = spec(required_skills=(SkillReq(SKILL, "پایتون", min_level=5, weight=3),))
    strong = spec()

    ranked = service.rank(student, [weak, strong], now=NOW)
    assert [m.project.id for m in ranked] == [strong.id, weak.id]


def test_rank_drops_excluded_projects() -> None:
    blocked = spec(required_assets=(AssetReq(uuid.uuid4(), "وانت", is_mandatory=True),))
    ranked = service.rank(ctx(), [blocked, spec()], now=NOW)

    assert blocked.id not in {m.project.id for m in ranked}


def test_rank_attaches_reasons() -> None:
    ranked = service.rank(ctx(), [spec()], now=NOW)
    assert ranked[0].reasons


def test_rank_is_stable_for_tied_scores() -> None:
    """مساوی‌ها با شناسه مرتب می‌شوند تا ترتیب بین دو فراخوانی عوض نشود."""
    first, second = spec(), spec()
    order_a = [m.project.id for m in service.rank(ctx(), [first, second], now=NOW)]
    order_b = [m.project.id for m in service.rank(ctx(), [second, first], now=NOW)]
    assert order_a == order_b


def test_rank_respects_limit() -> None:
    specs = [spec() for _ in range(15)]
    assert len(service.rank(ctx(), specs, now=NOW, limit=5)) == 5


# ── کدگذاری کش ─────────────────────────────────────────────────────────
def test_cache_round_trip_preserves_scores_and_reasons() -> None:
    """کش نباید امتیاز یا متن دلیل را عوض کند — §8.12."""
    student = ctx()
    original = service.rank(student, [spec(), spec()], now=NOW)

    payload = json.loads(service._encode(original, NOW))
    restored, computed_at = service._decode(payload)

    assert computed_at == NOW
    assert [m.score for m in restored] == [m.score for m in original]
    assert [m.project.id for m in restored] == [m.project.id for m in original]
    assert [[r.text for r in m.reasons] for m in restored] == [
        [r.text for r in m.reasons] for m in original
    ]
    assert restored[0].breakdown == original[0].breakdown


def test_cache_key_is_namespaced() -> None:
    assert service.key_recommendations(USER).startswith("silp:rec:")


# ── کوئری نامزد ────────────────────────────────────────────────────────
def test_candidate_query_filters_open_projects_and_capacity() -> None:
    sql = str(service.candidate_query(ctx(), now=NOW))

    assert "projects.status" in sql
    assert "projects.deleted_at IS NULL" in sql
    assert "team_size_max" in sql


def test_candidate_query_skips_the_asset_gate_before_step_two() -> None:
    """§8.3 — تا وقتی دانشجو امکاناتش را نگفته، دروازه اعمال نمی‌شود.

    وگرنه کاربری که تازه گام ۱ را زده هیچ نامزدی نمی‌گیرد، چون هر شش
    پروژهٔ §14.5 لپ‌تاپ را الزامی کرده‌اند.
    """
    sql = str(service.candidate_query(ctx(assets=frozenset()), now=NOW))
    assert "project_required_assets" not in sql


def test_candidate_query_applies_the_asset_gate_after_step_two() -> None:
    sql = str(service.candidate_query(ctx(assets=frozenset({ASSET})), now=NOW))
    assert "project_required_assets" in sql
    assert "NOT IN" in sql.upper()


def test_candidate_query_limit_is_bounded() -> None:
    assert "LIMIT" in str(service.candidate_query(ctx(), now=NOW)).upper()


# ── پیشنهادهای بازخوردخورده ────────────────────────────────────────────
def test_rank_excludes_dismissed_but_keeps_not_relevant() -> None:
    hidden, demoted, normal = spec(), spec(), spec()
    student = ctx(
        feedback={hidden.id: Verdict.DISMISSED, demoted.id: Verdict.NOT_RELEVANT},
    )
    ranked = service.rank(student, [hidden, demoted, normal], now=NOW)
    ids = [m.project.id for m in ranked]

    assert hidden.id not in ids
    assert ids == [normal.id, demoted.id]


# ── کمک‌های متن فارسی ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("value", "expected"),
    [(5, "۵"), (12, "۱۲"), ("سطح 3", "سطح ۳"), (2.5, "۲٫۵")],
)
def test_persian_digits(value: object, expected: str) -> None:
    assert to_persian_digits(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("parts", "expected"),
    [([], ""), (["الف"], "الف"), (["الف", "ب"], "الف و ب"), (["الف", "ب", "ج"], "الف، ب و ج")],
)
def test_join_fa(parts: list[str], expected: str) -> None:
    assert join_fa(parts) == expected
