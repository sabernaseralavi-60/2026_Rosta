"""مسیر /me — §5.3.

بخش هویتی از M0 است؛ نیمرخ و ارزیابی چهارگامی در M1، امتیاز در M5 و
شمارندهٔ اعلان در M6 افزوده شده.

مسیرهای امتیاز، نشان و داشبورد زیر همین `/me` در `gamification.py` هستند.

هر گام ارزیابی، بلافاصله **پیشنهاد** برمی‌گرداند — «لحظهٔ طلایی» §01.
این تنها دلیلی است که مسیر نیمرخ به موتور توصیه‌گر وابسته است.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.security import mask_email, mask_mobile
from silp.domain.recommendation import service as recommendation
from silp.models.identity import User
from silp.models.profile import DEGREE_TITLE_FA, TOTAL_SURVEY_STEPS, Profile
from silp.routers.deps import AuthServiceDep, CurrentUserDep, ProfileServiceDep, SessionDep
from silp.routers.v1.projects import project_summary_of
from silp.schemas.auth import MeOut, OnboardingOut, RoleGrantOut
from silp.schemas.common import ErrorResponse
from silp.schemas.gamification import MePointsOut
from silp.schemas.profile import (
    AssetsStepIn,
    InterestsStepIn,
    PreferencesStepIn,
    ProfileOut,
    ProfileUpdateIn,
    SkillsStepIn,
    SurveyOut,
    SurveyStepOut,
    UniversityRef,
)
from silp.schemas.project import RecommendationItemOut, breakdown_of, reasons_of
from silp.services.notification_service import NotificationService
from silp.services.points_service import PointsService
from silp.services.profile_service import InterestAnswer, SkillAnswer

router = APIRouter(
    prefix="/me",
    tags=["me"],
    responses={401: {"model": ErrorResponse, "description": "احراز هویت نشده"}},
)


def _profile_out(profile: Profile | None) -> ProfileOut | None:
    if profile is None:
        return None
    return ProfileOut(
        first_name=profile.first_name,
        last_name=profile.last_name,
        display_name=profile.display_name,
        university=(
            UniversityRef(id=profile.university.id, title_fa=profile.university.title_fa)
            if profile.university
            else None
        ),
        field_of_study=profile.field_of_study,
        degree_level=profile.degree_level,
        degree_level_fa=DEGREE_TITLE_FA.get(profile.degree_level or ""),
        entry_year=profile.entry_year,
        bio=profile.bio,
        work_style=profile.work_style,
        primary_goal=profile.primary_goal,
        weekly_hours=profile.weekly_hours,
        is_public=profile.is_public,
    )


@router.get("", response_model=MeOut, summary="اطلاعات کاربر جاری")
async def get_me(
    current: CurrentUserDep,
    session: SessionDep,
    auth: AuthServiceDep,
    profiles: ProfileServiceDep,
) -> MeOut:
    """اطلاعات تماس پوشانده برمی‌گردد (NFR-01): `0912***4567`."""
    user = await session.get(User, current.id)
    if user is None or user.deleted_at is not None:
        raise NotFound("کاربر پیدا نشد.")

    onboarding = await auth.onboarding_for(user)
    profile = await profiles.get(current.id)
    level = (await PointsService(session).summary(current.id)).level

    return MeOut(
        id=user.id,
        mobile=mask_mobile(user.mobile),
        email=mask_email(user.email),
        email_verified=user.email_verified_at is not None,
        mobile_verified=user.mobile_verified_at is not None,
        username=user.username,
        profile=_profile_out(profile),
        roles=[
            RoleGrantOut(
                code=grant.role.value,
                scope_type=grant.scope_type.value,
                scope_id=grant.scope_id,
            )
            for grant in current.grants
        ],
        onboarding=OnboardingOut(
            state=onboarding.state.value,
            completed_steps=onboarding.completed_steps,
            total_steps=onboarding.total_steps,
            next_route=onboarding.next_route,
        ),
        points=MePointsOut(total=level.total, level=level.level, next_level_at=level.next_at),
        unread_notifications=await NotificationService(session).unread_count(current.id),
    )


@router.patch("/profile", response_model=ProfileOut, summary="به‌روزرسانی اطلاعات پایه")
async def update_profile(
    payload: ProfileUpdateIn,
    current: CurrentUserDep,
    profiles: ProfileServiceDep,
) -> ProfileOut:
    """`PATCH` جزئی — فیلدهای نفرستاده دست‌نخورده می‌مانند (§5.3)."""
    profile = await profiles.upsert_basic(current.id, **payload.model_dump(exclude_unset=True))
    result = _profile_out(profile)
    if result is None:  # pragma: no cover — upsert_basic همیشه نیمرخ برمی‌گرداند
        raise NotFound("نیمرخ ساخته نشد.")
    return result


@router.get("/survey", response_model=SurveyOut, summary="وضعیت کامل ارزیابی نیمرخ")
async def get_survey(current: CurrentUserDep, profiles: ProfileServiceDep) -> SurveyOut:
    return SurveyOut.model_validate(await profiles.survey_state(current.id))


async def _step_result(
    session: AsyncSession, user_id: uuid.UUID, completed_steps: int
) -> SurveyStepOut:
    """پاسخ مشترک هر چهار گام — §5.3.

    پیشنهادها اینجا و نه در کلاینت گرفته می‌شوند تا دانشجو بلافاصله پس از
    ذخیره، ارزش گام را ببیند (اصل ۱ §00).
    """
    matches = await recommendation.preview(session, user_id)
    return SurveyStepOut(
        completed_steps=completed_steps,
        total_steps=TOTAL_SURVEY_STEPS,
        preview_recommendations=[
            RecommendationItemOut(
                project=project_summary_of(m.project),
                match_score=round(m.score, 1),
                reasons=reasons_of(m),
                breakdown=breakdown_of(m),
                is_stretch=m.is_stretch,
            )
            for m in matches
        ],
    )


@router.patch("/survey/skills", response_model=SurveyStepOut, summary="گام ۱ — مهارت‌ها")
async def save_skills(
    payload: SkillsStepIn,
    current: CurrentUserDep,
    session: SessionDep,
    profiles: ProfileServiceDep,
) -> SurveyStepOut:
    profile = await profiles.save_skills(
        current.id, [SkillAnswer(skill_id=a.skill_id, level=a.level) for a in payload.skills]
    )
    return await _step_result(session, current.id, profile.survey_completed_steps)


@router.patch("/survey/assets", response_model=SurveyStepOut, summary="گام ۲ — امکانات")
async def save_assets(
    payload: AssetsStepIn,
    current: CurrentUserDep,
    session: SessionDep,
    profiles: ProfileServiceDep,
) -> SurveyStepOut:
    profile = await profiles.save_assets(current.id, payload.asset_ids)
    return await _step_result(session, current.id, profile.survey_completed_steps)


@router.patch("/survey/interests", response_model=SurveyStepOut, summary="گام ۳ — علاقه‌ها")
async def save_interests(
    payload: InterestsStepIn,
    current: CurrentUserDep,
    session: SessionDep,
    profiles: ProfileServiceDep,
) -> SurveyStepOut:
    profile = await profiles.save_interests(
        current.id,
        [InterestAnswer(interest_id=a.interest_id, level=a.level) for a in payload.interests],
    )
    return await _step_result(session, current.id, profile.survey_completed_steps)


@router.patch("/survey/preferences", response_model=SurveyStepOut, summary="گام ۴ — ترجیحات")
async def save_preferences(
    payload: PreferencesStepIn,
    current: CurrentUserDep,
    session: SessionDep,
    profiles: ProfileServiceDep,
) -> SurveyStepOut:
    profile = await profiles.save_preferences(
        current.id,
        work_style=payload.work_style,
        primary_goal=payload.primary_goal,
        weekly_hours=payload.weekly_hours,
    )
    return await _step_result(session, current.id, profile.survey_completed_steps)


__all__ = ["router"]
