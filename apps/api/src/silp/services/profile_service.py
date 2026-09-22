"""نیمرخ و ارزیابی چهارگامی — FR-PROF-01، §5.3، §7.1.

هر گام مستقل ذخیره می‌شود و `survey_completed_steps` **هرگز کم نمی‌شود**:
دانشجویی که گام ۳ را ویرایش می‌کند، نباید ناگهان «۲ گام» ببیند.

پیش از هر نوشتن روی ارزیابی، یک نسخه از وضعیت پیشین در
`profile_survey_versions` ذخیره می‌شود (FR-PROF-01).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.domain.identity.onboarding import ProfileSnapshot
from silp.domain.recommendation import service as recommendation
from silp.models.profile import (
    TOTAL_SURVEY_STEPS,
    Profile,
    ProfileAsset,
    ProfileInterest,
    ProfileSkill,
    ProfileSurveyVersion,
)
from silp.models.taxonomy import Asset, Interest, Skill
from silp.services import events

log = get_logger("silp.profile")

SKILLS_STEP = 1
ASSETS_STEP = 2
INTERESTS_STEP = 3
PREFERENCES_STEP = 4


@dataclass(frozen=True, slots=True)
class SkillAnswer:
    skill_id: uuid.UUID
    level: int


@dataclass(frozen=True, slots=True)
class InterestAnswer:
    interest_id: uuid.UUID
    level: int


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── خواندن ─────────────────────────────────────────────────────────
    async def get(self, user_id: uuid.UUID) -> Profile | None:
        return await self.session.get(Profile, user_id)

    async def require(self, user_id: uuid.UUID) -> Profile:
        profile = await self.get(user_id)
        if profile is None:
            raise NotFound("هنوز نیمرخی نساخته‌اید.")
        return profile

    async def snapshot_for_onboarding(self, user_id: uuid.UUID) -> ProfileSnapshot | None:
        """کمینهٔ اطلاعاتی که §7.1 برای تصمیم ورود اولیه لازم دارد."""
        profile = await self.get(user_id)
        if profile is None:
            return None
        return ProfileSnapshot(
            first_name=profile.first_name,
            last_name=profile.last_name,
            survey_completed_steps=profile.survey_completed_steps,
        )

    # ── اطلاعات پایه ───────────────────────────────────────────────────
    async def upsert_basic(self, user_id: uuid.UUID, **fields: Any) -> Profile:
        """ساخت یا به‌روزرسانی جزئی نیمرخ — `PATCH /me/profile`.

        فقط کلیدهای فرستاده‌شده تغییر می‌کنند؛ `None` یعنی «دست نزن»، نه
        «خالی کن». پاک کردن یک فیلد در §5.3 مسیر جداگانه دارد.
        """
        known = {k: v for k, v in fields.items() if v is not None}
        profile = await self.get(user_id)

        if profile is None:
            if not known.get("first_name") or not known.get("last_name"):
                raise ValidationFailed("نام و نام خانوادگی برای ساخت نیمرخ لازم است.")
            profile = Profile(user_id=user_id, **known)
            self.session.add(profile)
            await self.session.commit()
            log.info("profile_created", user_id=str(user_id))
            return profile

        for key, value in known.items():
            setattr(profile, key, value)
        await self.session.commit()
        return profile

    # ── گام‌های ارزیابی ────────────────────────────────────────────────
    async def save_skills(self, user_id: uuid.UUID, answers: list[SkillAnswer]) -> Profile:
        """گام ۱ — ثبت جزئی مجاز است؛ مهارت‌های نفرستاده دست‌نخورده می‌مانند."""
        profile = await self.require(user_id)
        await self._archive(user_id)
        await self._validate_ids(Skill, [a.skill_id for a in answers], "مهارت")

        for answer in answers:
            await self.session.execute(
                insert(ProfileSkill)
                .values(user_id=user_id, skill_id=answer.skill_id, level=answer.level)
                .on_conflict_do_update(
                    index_elements=[ProfileSkill.user_id, ProfileSkill.skill_id],
                    # ویرایش سطح، تأیید قبلی استاد را باطل می‌کند: شواهد
                    # مربوط به سطح قدیم بود (FR-PROF-04).
                    set_={
                        "level": answer.level,
                        "verified_by": None,
                        "verified_at": None,
                        "evidence_type": None,
                        "evidence_id": None,
                        "updated_at": datetime.now(UTC),
                    },
                )
            )
        return await self._mark_step(profile, SKILLS_STEP)

    async def save_assets(self, user_id: uuid.UUID, asset_ids: list[uuid.UUID]) -> Profile:
        """گام ۲ — جایگزینی کامل. فهرست خالی یعنی «هیچ امکانی ندارم»."""
        profile = await self.require(user_id)
        await self._archive(user_id)
        await self._validate_ids(Asset, asset_ids, "امکانات")

        await self.session.execute(delete(ProfileAsset).where(ProfileAsset.user_id == user_id))
        for asset_id in dict.fromkeys(asset_ids):
            self.session.add(ProfileAsset(user_id=user_id, asset_id=asset_id))
        return await self._mark_step(profile, ASSETS_STEP)

    async def save_interests(self, user_id: uuid.UUID, answers: list[InterestAnswer]) -> Profile:
        """گام ۳ — مثل گام ۱، ثبت جزئی."""
        profile = await self.require(user_id)
        await self._archive(user_id)
        await self._validate_ids(Interest, [a.interest_id for a in answers], "حوزهٔ علاقه")

        for answer in answers:
            await self.session.execute(
                insert(ProfileInterest)
                .values(user_id=user_id, interest_id=answer.interest_id, level=answer.level)
                .on_conflict_do_update(
                    index_elements=[ProfileInterest.user_id, ProfileInterest.interest_id],
                    set_={"level": answer.level},
                )
            )
        return await self._mark_step(profile, INTERESTS_STEP)

    async def save_preferences(
        self,
        user_id: uuid.UUID,
        *,
        work_style: str | None = None,
        primary_goal: str | None = None,
        weekly_hours: int | None = None,
    ) -> Profile:
        """گام ۴ — سبک کار، هدف اصلی، زمان در دسترس."""
        profile = await self.require(user_id)
        await self._archive(user_id)

        if work_style is not None:
            profile.work_style = work_style
        if primary_goal is not None:
            profile.primary_goal = primary_goal
        if weekly_hours is not None:
            profile.weekly_hours = weekly_hours

        return await self._mark_step(profile, PREFERENCES_STEP)

    # ── وضعیت کامل ارزیابی ─────────────────────────────────────────────
    async def survey_state(self, user_id: uuid.UUID) -> dict[str, Any]:
        """`GET /me/survey` — همهٔ پاسخ‌ها به‌علاوهٔ ترجیحات."""
        skills = (
            await self.session.execute(
                select(ProfileSkill.skill_id, ProfileSkill.level, ProfileSkill.verified_at).where(
                    ProfileSkill.user_id == user_id
                )
            )
        ).all()
        assets = (
            await self.session.scalars(
                select(ProfileAsset.asset_id).where(ProfileAsset.user_id == user_id)
            )
        ).all()
        interests = (
            await self.session.execute(
                select(ProfileInterest.interest_id, ProfileInterest.level).where(
                    ProfileInterest.user_id == user_id
                )
            )
        ).all()
        profile = await self.get(user_id)

        return {
            "skills": [
                {
                    "skill_id": row.skill_id,
                    "level": row.level,
                    "is_verified": row.verified_at is not None,
                }
                for row in skills
            ],
            "asset_ids": list(assets),
            "interests": [
                {"interest_id": row.interest_id, "level": row.level} for row in interests
            ],
            "work_style": profile.work_style if profile else None,
            "primary_goal": profile.primary_goal if profile else None,
            "weekly_hours": profile.weekly_hours if profile else None,
            "completed_steps": profile.survey_completed_steps if profile else 0,
            "total_steps": TOTAL_SURVEY_STEPS,
        }

    # ── کمکی‌ها ────────────────────────────────────────────────────────
    async def _mark_step(self, profile: Profile, step: int) -> Profile:
        """شمارندهٔ گام هرگز کم نمی‌شود — ویرایش گام قدیمی پیشرفت را نمی‌خورد.

        `commit` اینجاست، نه در مسیر: هر گام یک تراکنش کامل است و پاسخ‌ها،
        نسخهٔ آرشیو و شمارنده با هم تثبیت می‌شوند یا هیچ‌کدام.
        """
        profile.survey_completed_steps = max(profile.survey_completed_steps, step)
        profile.survey_updated_at = datetime.now(UTC)
        await events.publish(
            self.session,
            events.SurveyStepCompleted(
                user_id=profile.user_id, completed_steps=profile.survey_completed_steps
            ),
        )
        await self.session.commit()
        # §8.12 — نیمرخ عوض شد، پیشنهادهای کش‌شده دیگر معتبر نیستند.
        # پس از commit انجام می‌شود تا کش، وضعیتی را نشکند که هنوز نوشته نشده.
        await recommendation.invalidate(profile.user_id)
        return profile

    async def _archive(self, user_id: uuid.UUID) -> None:
        """نگه‌داشتن وضعیت پیش از ویرایش — FR-PROF-01.

        اولین پر کردن یک گام آرشیو نمی‌شود: عکس گرفتن از نیمرخ خالی چیزی
        به تحلیل رشد مهارت اضافه نمی‌کند.
        """
        state = await self.survey_state(user_id)
        if not state["skills"] and not state["asset_ids"] and not state["interests"]:
            return

        self.session.add(
            ProfileSurveyVersion(
                user_id=user_id,
                snapshot={
                    "skills": [
                        {"skill_id": str(s["skill_id"]), "level": s["level"]}
                        for s in state["skills"]
                    ],
                    "asset_ids": [str(a) for a in state["asset_ids"]],
                    "interests": [
                        {"interest_id": str(i["interest_id"]), "level": i["level"]}
                        for i in state["interests"]
                    ],
                    "work_style": state["work_style"],
                    "primary_goal": state["primary_goal"],
                    "weekly_hours": state["weekly_hours"],
                    "completed_steps": state["completed_steps"],
                },
            )
        )

    async def _validate_ids(
        self, model: type[Skill] | type[Asset] | type[Interest], ids: list[uuid.UUID], label: str
    ) -> None:
        """شناسهٔ ناموجود باید ۴۲۲ بدهد، نه ۵۰۰ از کلید خارجی."""
        if not ids:
            return
        found = set(
            (await self.session.scalars(select(model.id).where(model.id.in_(set(ids))))).all()
        )
        missing = set(ids) - found
        if missing:
            raise ValidationFailed(
                f"{label} انتخاب‌شده معتبر نیست.",
                details={"unknown_ids": sorted(str(i) for i in missing)},
            )


__all__ = [
    "ASSETS_STEP",
    "INTERESTS_STEP",
    "PREFERENCES_STEP",
    "SKILLS_STEP",
    "InterestAnswer",
    "ProfileService",
    "SkillAnswer",
]
