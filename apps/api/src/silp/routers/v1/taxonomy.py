"""مسیر /taxonomy — §5.4.

بدون احراز هویت: فرم ثبت‌نام باید پیش از ورود هم این فهرست‌ها را بگیرد.
همه با `Cache-Control: public, max-age=3600` پاسخ می‌دهند؛ این جدول‌ها
ماه‌ها ثابت‌اند و هر درخواست اضافه به آن‌ها اتلاف است.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from silp.models.taxonomy import (
    INTEREST_LEVEL_LABELS,
    SKILL_LEVEL_LABELS,
    Asset,
    Interest,
    Skill,
    University,
)
from silp.routers.deps import SessionDep
from silp.schemas.taxonomy import (
    AssetOut,
    InterestListOut,
    InterestOut,
    LevelLabel,
    SkillListOut,
    SkillOut,
    UniversityOut,
)

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])

CACHE_HEADER = "public, max-age=3600"
UNIVERSITY_SEARCH_LIMIT = 30
MIN_SEARCH_LENGTH = 2

_SKILL_LEVELS = [LevelLabel(level=k, label=v) for k, v in sorted(SKILL_LEVEL_LABELS.items())]
_INTEREST_LEVELS = [LevelLabel(level=k, label=v) for k, v in sorted(INTEREST_LEVEL_LABELS.items())]


@router.get("/skills", response_model=SkillListOut, summary="فهرست مهارت‌ها")
async def list_skills(session: SessionDep, response: Response) -> SkillListOut:
    response.headers["Cache-Control"] = CACHE_HEADER
    rows = await session.scalars(
        select(Skill).where(Skill.is_active.is_(True)).order_by(Skill.sort_order, Skill.code)
    )
    return SkillListOut(
        items=[SkillOut.model_validate(r) for r in rows],
        level_labels=_SKILL_LEVELS,
    )


@router.get("/assets", response_model=list[AssetOut], summary="فهرست امکانات")
async def list_assets(session: SessionDep, response: Response) -> list[AssetOut]:
    response.headers["Cache-Control"] = CACHE_HEADER
    rows = await session.scalars(
        select(Asset).where(Asset.is_active.is_(True)).order_by(Asset.sort_order, Asset.code)
    )
    return [AssetOut.model_validate(r) for r in rows]


@router.get("/interests", response_model=InterestListOut, summary="فهرست حوزه‌های علاقه")
async def list_interests(session: SessionDep, response: Response) -> InterestListOut:
    response.headers["Cache-Control"] = CACHE_HEADER
    rows = await session.scalars(
        select(Interest)
        .where(Interest.is_active.is_(True))
        .order_by(Interest.sort_order, Interest.code)
    )
    return InterestListOut(
        items=[InterestOut.model_validate(r) for r in rows],
        level_labels=_INTEREST_LEVELS,
    )


@router.get("/universities", response_model=list[UniversityOut], summary="جستجوی دانشگاه")
async def search_universities(
    session: SessionDep,
    response: Response,
    q: Annotated[str | None, Query(max_length=100, description="بخشی از نام دانشگاه")] = None,
) -> list[UniversityOut]:
    """جستجو با `fa_normalize` انجام می‌شود، نه `ILIKE` خام.

    کاربر «دانشگاه شهيد باهنر» با «ي» عربی می‌نویسد و باید همان نتیجه را
    بگیرد که با «ی» فارسی — §4.11.
    """
    response.headers["Cache-Control"] = CACHE_HEADER

    stmt = select(University).where(University.is_active.is_(True))
    if q and len(q.strip()) >= MIN_SEARCH_LENGTH:
        normalized = func.fa_normalize(q.strip())
        stmt = stmt.where(
            func.fa_normalize(University.title_fa).like(func.concat("%", normalized, "%"))
        )

    rows = await session.scalars(stmt.order_by(University.title_fa).limit(UNIVERSITY_SEARCH_LIMIT))
    return [UniversityOut.model_validate(r) for r in rows]


__all__ = ["router"]
