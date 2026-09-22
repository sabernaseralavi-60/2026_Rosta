"""مسیر /subscriptions — ADR-0009.

سه مخاطب:

* **همه** — `GET /subscriptions/plans`: طرح‌ها و قیمت‌ها، بدون ورود.
* **کاربر** — `GET|POST /subscriptions`: وضعیت و درخواست اشتراک.
* **پشتیبانی** — `POST /subscriptions/grant` و `/{id}/activate`: تأیید
  پرداختی که بیرون از سامانه انجام شده (§02).

هیچ endpointی اینجا پول جابه‌جا نمی‌کند. درگاه پرداخت در فاز ۲ می‌آید
و آن‌وقت فقط `activate` یک صداکنندهٔ تازه پیدا می‌کند.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Permission
from silp.models.access import (
    PLAN_SCOPE_TITLE_FA,
    SUBSCRIPTION_STATUS_TITLE_FA,
    Subscription,
    SubscriptionPlan,
)
from silp.models.education import Course
from silp.routers.deps import (
    CurrentUserDep,
    EntitlementServiceDep,
    SessionDep,
    SubscriptionServiceDep,
    require,
)
from silp.schemas.access import (
    RIAL_PER_TOMAN,
    MySubscriptionsOut,
    PlanOut,
    SubscriptionActivateIn,
    SubscriptionGrantIn,
    SubscriptionOut,
    SubscriptionRequestIn,
)
from silp.schemas.common import ErrorResponse
from silp.services.entitlement_service import EntitlementService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

SECONDS_PER_DAY = 86400


def _format_price(price_irr: int) -> str:
    """قیمت خوانا به تومان — «۲۹۰٬۰۰۰ تومان» یا «رایگان»."""
    if price_irr <= 0:
        return "رایگان"
    toman = price_irr // RIAL_PER_TOMAN
    return f"{toman:,} تومان".replace(",", "٬")


def plan_out(plan: SubscriptionPlan) -> PlanOut:
    return PlanOut(
        id=plan.id,
        code=plan.code,
        title_fa=plan.title_fa,
        description=plan.description,
        scope=plan.scope,
        scope_fa=PLAN_SCOPE_TITLE_FA.get(plan.scope, plan.scope),
        duration_days=plan.duration_days,
        price_irr=plan.price_irr,
        price_toman=plan.price_irr // RIAL_PER_TOMAN,
        price_fa=_format_price(plan.price_irr),
    )


def subscription_out(
    subscription: Subscription,
    plan: SubscriptionPlan,
    course_title: str | None,
    *,
    now: datetime,
) -> SubscriptionOut:
    remaining = max(0, int((subscription.ends_at - now).total_seconds() // SECONDS_PER_DAY))
    return SubscriptionOut(
        id=subscription.id,
        plan_code=plan.code,
        plan_title_fa=plan.title_fa,
        course_id=subscription.course_id,
        course_title_fa=course_title,
        status=subscription.status,
        status_fa=SUBSCRIPTION_STATUS_TITLE_FA.get(subscription.status, subscription.status),
        starts_at=subscription.starts_at,
        ends_at=subscription.ends_at,
        days_remaining=remaining,
        payment_ref=subscription.payment_ref,
        amount_irr=subscription.amount_irr,
    )


@router.get("/plans", response_model=list[PlanOut], summary="طرح‌های اشتراک")
async def list_plans(subscriptions: SubscriptionServiceDep, response: Response) -> list[PlanOut]:
    """بدون ورود هم کار می‌کند — صفحهٔ قیمت باید برای مهمان باز باشد."""
    response.headers["Cache-Control"] = "public, max-age=600"
    return [plan_out(plan) for plan in await subscriptions.active_plans()]


@router.get("", response_model=MySubscriptionsOut, summary="اشتراک‌های من")
async def my_subscriptions(
    subscriptions: SubscriptionServiceDep,
    entitlements: EntitlementServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> MySubscriptionsOut:
    rows = await subscriptions.mine(current.id)
    return await _render(session, rows, user=current, entitlements=entitlements)


async def _render(
    session: AsyncSession,
    rows: list[Subscription],
    *,
    user: CurrentUser,
    entitlements: EntitlementService,
) -> MySubscriptionsOut:
    now = datetime.now(UTC)
    plans = {
        plan.id: plan
        for plan in await session.scalars(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id.in_([r.plan_id for r in rows] or [uuid.UUID(int=0)])
            )
        )
    }
    course_titles: dict[uuid.UUID, str] = {
        course.id: course.title_fa
        for course in await session.scalars(
            select(Course).where(
                Course.id.in_([r.course_id for r in rows if r.course_id] or [uuid.UUID(int=0)])
            )
        )
    }
    ctx = await entitlements.context_for(user)
    items = [
        subscription_out(
            row,
            plans[row.plan_id],
            course_titles.get(row.course_id) if row.course_id else None,
            now=now,
        )
        for row in rows
        if row.plan_id in plans
    ]
    return MySubscriptionsOut(
        has_active=ctx.has_global_subscription or bool(ctx.subscribed_course_ids),
        covers_all_courses=ctx.has_global_subscription,
        items=items,
    )


@router.post(
    "",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="درخواست اشتراک",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def request_subscription(
    payload: SubscriptionRequestIn,
    subscriptions: SubscriptionServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> SubscriptionOut:
    """ثبت درخواست — وضعیت `PENDING` تا تأیید پرداخت بیرونی.

    پاسخ عمداً یک ردیف «در انتظار» است و نه یک دسترسی باز: کاربر باید
    ببیند که چیزی ثبت شده و منتظر چیست.
    """
    plan = await subscriptions.plan_by_code(payload.plan_code)
    course_id = await _course_id_of(session, payload.course_slug)
    subscription = await subscriptions.request(
        user_id=current.id, plan_id=plan.id, course_id=course_id, note=payload.note
    )
    title = await _course_title(session, course_id)
    return subscription_out(subscription, plan, title, now=datetime.now(UTC))


@router.delete(
    "/{subscription_id}",
    response_model=SubscriptionOut,
    summary="لغو اشتراک",
    responses={404: {"model": ErrorResponse}},
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    subscriptions: SubscriptionServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> SubscriptionOut:
    subscription = await subscriptions.cancel(subscription_id=subscription_id, user_id=current.id)
    plan = await session.get(SubscriptionPlan, subscription.plan_id)
    if plan is None:  # pragma: no cover — کلید خارجی تضمینش می‌کند
        raise NotFound("طرح این اشتراک پیدا نشد.")
    title = await _course_title(session, subscription.course_id)
    return subscription_out(subscription, plan, title, now=datetime.now(UTC))


# ── پشتیبانی ───────────────────────────────────────────────────────────
@router.post(
    "/grant",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="فعال‌سازی اشتراک برای یک کاربر",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def grant_subscription(
    payload: SubscriptionGrantIn,
    subscriptions: SubscriptionServiceDep,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.SUBSCRIPTION_GRANT))],
) -> SubscriptionOut:
    """§02 — «پرداخت خارج از سامانه انجام می‌شود».

    `payment_ref` شمارهٔ فیش یا کد رهگیری است و **باید** پر شود مگر
    اشتراک هدیه باشد؛ بدون آن، بعداً معلوم نیست چرا فعال شده.
    """
    plan = await subscriptions.plan_by_code(payload.plan_code)
    course_id = await _course_id_of(session, payload.course_slug)
    subscription = await subscriptions.grant(
        user_id=payload.user_id,
        plan_id=plan.id,
        granted_by=actor.id,
        course_id=course_id,
        payment_ref=payload.payment_ref,
        note=payload.note,
    )
    title = await _course_title(session, course_id)
    return subscription_out(subscription, plan, title, now=datetime.now(UTC))


@router.post(
    "/{subscription_id}/activate",
    response_model=SubscriptionOut,
    summary="تأیید پرداخت و فعال‌سازی",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def activate_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionActivateIn,
    subscriptions: SubscriptionServiceDep,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.SUBSCRIPTION_GRANT))],
) -> SubscriptionOut:
    subscription = await subscriptions.activate(
        subscription_id=subscription_id,
        granted_by=actor.id,
        payment_ref=payload.payment_ref,
    )
    plan = await session.get(SubscriptionPlan, subscription.plan_id)
    if plan is None:  # pragma: no cover
        raise NotFound("طرح این اشتراک پیدا نشد.")
    title = await _course_title(session, subscription.course_id)
    return subscription_out(subscription, plan, title, now=datetime.now(UTC))


@router.get(
    "/pending",
    response_model=list[SubscriptionOut],
    summary="درخواست‌های اشتراک در انتظار تأیید",
    responses={403: {"model": ErrorResponse}},
)
async def pending_subscriptions(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.SUBSCRIPTION_VIEW_ALL))],
) -> list[SubscriptionOut]:
    rows = list(
        await session.scalars(
            select(Subscription)
            .where(Subscription.status == "PENDING")
            .order_by(Subscription.created_at)
        )
    )
    now = datetime.now(UTC)
    plans = {
        plan.id: plan
        for plan in await session.scalars(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id.in_([r.plan_id for r in rows] or [uuid.UUID(int=0)])
            )
        )
    }
    return [
        subscription_out(
            row, plans[row.plan_id], await _course_title(session, row.course_id), now=now
        )
        for row in rows
        if row.plan_id in plans
    ]


# ── کمکی ───────────────────────────────────────────────────────────────
async def _course_id_of(session: AsyncSession, slug: str | None) -> uuid.UUID | None:
    if not slug:
        return None
    course_id: uuid.UUID | None = await session.scalar(
        select(Course.id).where(Course.slug == slug, Course.deleted_at.is_(None))
    )
    if course_id is None:
        raise NotFound("درس انتخاب‌شده پیدا نشد.")
    return course_id


async def _course_title(session: AsyncSession, course_id: uuid.UUID | None) -> str | None:
    if course_id is None:
        return None
    title: str | None = await session.scalar(select(Course.title_fa).where(Course.id == course_id))
    return title


__all__ = ["plan_out", "router", "subscription_out"]
