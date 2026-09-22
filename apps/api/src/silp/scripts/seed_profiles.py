"""نیمرخ حساب‌های نمونهٔ توسعه — §14.8 و پرسوناهای §01.

هر پرسونا طوری تنظیم شده که یک مسیر متفاوت از موتور توصیه‌گر را نشان دهد:

| حساب | پرسونا | انتظار |
|------|--------|--------|
| ۰۹۱۲۰۰۰۰۰۱۰ | مریم | هدف نمره، مهارت نرم‌افزاری متوسط ⇒ پروژهٔ نوع C |
| ۰۹۱۲۰۰۰۰۰۱۱ | امیر | R و آمار قوی، هدف مقاله ⇒ پروژهٔ نوع B |
| ۰۹۱۲۰۰۰۰۰۱۲ | سارا | فروش و محتوا، موتور دارد، هدف درآمد ⇒ پروژهٔ نوع A |
| ۰۹۱۲۰۰۰۰۰۱۳ | — | نیمرخ خالی، برای آزمایش جریان ورود اولیه |

حساب ۰۹۱۲۰۰۰۰۰۱۳ عمداً نیمرخ نمی‌گیرد: بدون آن، حالت
`BASIC_INFO_REQUIRED` هرگز دستی آزمایش نمی‌شود.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.models.identity import User
from silp.models.profile import Profile, ProfileAsset, ProfileInterest, ProfileSkill
from silp.models.taxonomy import Asset, Interest, Skill, University

log = get_logger("silp.seed.profiles")


@dataclass(frozen=True, slots=True)
class ProfileSeed:
    mobile: str
    first_name: str
    last_name: str
    field_of_study: str
    degree_level: str
    work_style: str
    primary_goal: str
    weekly_hours: int
    skills: dict[str, int] = field(default_factory=dict)
    assets: tuple[str, ...] = ()
    interests: dict[str, int] = field(default_factory=dict)


PROFILES: tuple[ProfileSeed, ...] = (
    ProfileSeed(
        mobile="09120000001",
        first_name="صابر",
        last_name="مدیر",
        field_of_study="مهندسی عمران",
        degree_level="PHD",
        work_style="EITHER",
        primary_goal="LEARNING",
        weekly_hours=20,
        skills={"PYTHON": 5, "STATISTICS": 5, "WRITING": 5, "MODELING": 5},
        assets=("LAPTOP", "POWERFUL_PC", "FAST_INTERNET", "CAR"),
        interests={"RESEARCH": 5, "TRANSPORT": 5, "URBAN": 5},
    ),
    ProfileSeed(
        mobile="09120000002",
        first_name="استاد",
        last_name="نمونه",
        field_of_study="مهندسی حمل‌ونقل",
        degree_level="PHD",
        work_style="TEAM",
        primary_goal="PUBLICATION",
        weekly_hours=15,
        skills={"SUMO": 5, "PYTHON": 4, "GIS": 4, "WRITING": 5, "ENGLISH": 5},
        assets=("LAPTOP", "FAST_INTERNET", "CAR"),
        interests={"RESEARCH": 5, "TRANSPORT": 5, "URBAN": 4},
    ),
    ProfileSeed(
        mobile="09120000010",
        first_name="مریم",
        last_name="کریمی",
        field_of_study="مهندسی عمران",
        degree_level="BACHELOR",
        work_style="TEAM",
        primary_goal="GRADE",
        weekly_hours=8,
        skills={"EXCEL": 3, "PYTHON": 2, "AUTOCAD": 3, "AI_TOOLS": 3, "ENGLISH": 3},
        assets=("LAPTOP", "FAST_INTERNET"),
        interests={"TRANSPORT": 4, "URBAN": 4, "DATA_ANALYSIS": 3, "PROJECT_MGMT": 3},
    ),
    ProfileSeed(
        mobile="09120000011",
        first_name="امیر",
        last_name="رضایی",
        field_of_study="مهندسی حمل‌ونقل",
        degree_level="MASTER",
        work_style="SOLO",
        primary_goal="PUBLICATION",
        weekly_hours=14,
        skills={"R": 5, "STATISTICS": 4, "PYTHON": 3, "WRITING": 4, "ENGLISH": 4},
        assets=("LAPTOP", "POWERFUL_PC", "FAST_INTERNET"),
        interests={"RESEARCH": 5, "DATA_ANALYSIS": 5, "TRANSPORT": 4, "PROGRAMMING": 3},
    ),
    ProfileSeed(
        mobile="09120000012",
        first_name="سارا",
        last_name="محمدی",
        field_of_study="مدیریت بازرگانی",
        degree_level="BACHELOR",
        work_style="TEAM",
        primary_goal="INCOME",
        weekly_hours=12,
        skills={"MARKETING_SKILL": 4, "GRAPHIC_DESIGN": 3, "EXCEL": 3, "PRESENTATION": 4},
        assets=("LAPTOP", "MOTORCYCLE", "CAMERA", "FAST_INTERNET"),
        interests={"SALES": 5, "MARKETING": 5, "CONTENT": 4, "COMMERCE": 4, "AGRICULTURE": 3},
    ),
    ProfileSeed(
        mobile="09120000020",
        first_name="کاربر",
        last_name="عمومی",
        field_of_study="—",
        degree_level="OTHER",
        work_style="SOLO",
        primary_goal="LEARNING",
        weekly_hours=5,
        skills={"EXCEL": 2, "ENGLISH": 2},
        assets=("LAPTOP",),
        interests={"COMMERCE": 3, "PROGRAMMING": 2},
    ),
)

DEFAULT_UNIVERSITY = "دانشگاه شهید باهنر کرمان"
COMPLETED_STEPS = 4


async def _code_map(
    session: AsyncSession, model: type[Skill] | type[Asset] | type[Interest]
) -> dict[str, uuid.UUID]:
    """نگاشت کد ← شناسه. داده‌های اولیه با کد نوشته شده‌اند، نه UUID:
    UUIDها در هر محیط فرق می‌کنند و در سند §14 جایی ندارند."""
    rows = (await session.execute(select(model.code, model.id))).all()
    return {row.code: row.id for row in rows}


async def seed_profiles(session: AsyncSession) -> tuple[int, int]:
    """ساخت نیمرخ برای حساب‌های نمونه. خروجی: (ساخته‌شده، از قبل موجود)."""
    skills = await _code_map(session, Skill)
    assets = await _code_map(session, Asset)
    interests = await _code_map(session, Interest)
    university_id = await session.scalar(
        select(University.id).where(University.title_fa == DEFAULT_UNIVERSITY)
    )

    created = 0
    existing = 0

    for seed in PROFILES:
        user_id = await session.scalar(select(User.id).where(User.mobile == seed.mobile))
        if user_id is None:
            log.warning("seed_profile_user_missing", mobile=seed.mobile)
            continue
        if await session.get(Profile, user_id) is not None:
            existing += 1
            continue

        session.add(
            Profile(
                user_id=user_id,
                first_name=seed.first_name,
                last_name=seed.last_name,
                university_id=university_id,
                field_of_study=seed.field_of_study,
                degree_level=seed.degree_level,
                work_style=seed.work_style,
                primary_goal=seed.primary_goal,
                weekly_hours=seed.weekly_hours,
                survey_completed_steps=COMPLETED_STEPS,
            )
        )
        for code, level in seed.skills.items():
            if code in skills:
                session.add(ProfileSkill(user_id=user_id, skill_id=skills[code], level=level))
        for code in seed.assets:
            if code in assets:
                session.add(ProfileAsset(user_id=user_id, asset_id=assets[code]))
        for code, level in seed.interests.items():
            if code in interests:
                session.add(
                    ProfileInterest(user_id=user_id, interest_id=interests[code], level=level)
                )

        created += 1
        log.info("seed_profile_created", mobile=seed.mobile, name=seed.first_name)

    return created, existing


__all__ = ["PROFILES", "ProfileSeed", "seed_profiles"]
