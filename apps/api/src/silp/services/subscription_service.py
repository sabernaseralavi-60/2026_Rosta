"""طرح‌های اشتراک و چرخهٔ اشتراک کاربر — ADR-0009.

**پرداخت اینجا انجام نمی‌شود.** §13.5 درگاه پرداخت را بیرون از فاز ۱
گذاشته است، پس چرخه دو گام دارد:

۱. کاربر `request()` می‌زند ⇒ ردیف `PENDING` با مبلغ و طرح.
۲. پشتیبانی پس از دیدن فیش، `activate()` می‌زند ⇒ `ACTIVE` با
   `payment_ref`.

وقتی درگاه آمد، گام ۲ را یک وب‌هوک می‌زند و هیچ چیز دیگری عوض
نمی‌شود — نه جدول، نه سنجش دسترسی، نه رابط کاربری.

**تمدید، نه جایگزینی:** اگر کاربر اشتراک فعال داشته باشد و دوباره
بخرد، دورهٔ تازه از پایان دورهٔ فعلی شروع می‌شود، نه از امروز. هیچ‌کس
نباید با زودتر تمدید کردن، روز از دست بدهد.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, PlanScopeMismatch, ValidationFailed
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser
from silp.domain import audit
from silp.models.access import Subscription, SubscriptionPlan
from silp.models.education import Course
from silp.services import events
from silp.services.audit_service import AuditService

log = get_logger("silp.subscriptions")

MIN_REJECT_REASON = 5


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── طرح‌ها ─────────────────────────────────────────────────────────
    async def active_plans(self) -> list[SubscriptionPlan]:
        rows = await self.session.scalars(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price_irr)
        )
        return list(rows)

    async def plan_by_code(self, code: str) -> SubscriptionPlan:
        plan = await self.session.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.code == code)
        )
        if plan is None:
            raise NotFound("این طرح اشتراک پیدا نشد.")
        return plan

    # ── درخواست و فعال‌سازی ────────────────────────────────────────────
    async def request(
        self,
        *,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        course_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> Subscription:
        """ثبت درخواست اشتراک — وضعیت `PENDING` تا تأیید پرداخت."""
        subscription, plan = await self._new_row(
            user_id=user_id, plan_id=plan_id, course_id=course_id, note=note
        )
        await self.session.commit()
        log.info("subscription_requested", plan=plan.code, user_id=str(user_id))
        return subscription

    async def _new_row(
        self,
        *,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        course_id: uuid.UUID | None,
        note: str | None,
    ) -> tuple[Subscription, SubscriptionPlan]:
        plan = await self.session.get(SubscriptionPlan, plan_id)
        if plan is None or not plan.is_active:
            raise NotFound("این طرح اشتراک پیدا نشد.")

        course_id = await self._validated_course(plan, course_id)

        starts_at = await self._next_start(user_id, course_id)
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            course_id=course_id,
            status="PENDING",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=plan.duration_days),
            amount_irr=plan.price_irr,
            note=note,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription, plan

    async def _validated_course(
        self, plan: SubscriptionPlan, course_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        """طرح تک‌درسی بدون درس، و طرح همه‌دروس با درس، هر دو غلط‌اند."""
        if plan.scope == "SINGLE_COURSE":
            if course_id is None:
                raise PlanScopeMismatch("برای این طرح باید یک درس انتخاب کنید.")
            course = await self.session.get(Course, course_id)
            if course is None or course.deleted_at is not None:
                raise NotFound("درس انتخاب‌شده پیدا نشد.")
            return course_id
        if course_id is not None:
            raise PlanScopeMismatch("طرح «همهٔ دروس» به انتخاب درس نیاز ندارد.")
        return None

    async def _next_start(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID | None,
        *,
        statuses: tuple[str, ...] = ("ACTIVE", "PENDING"),
        exclude: uuid.UUID | None = None,
    ) -> datetime:
        """شروع دورهٔ تازه: پایان دورهٔ فعلیِ هم‌دامنه، یا همین حالا."""
        now = _now()
        stmt = (
            select(Subscription.ends_at)
            .where(
                Subscription.user_id == user_id,
                Subscription.course_id.is_(None)
                if course_id is None
                else Subscription.course_id == course_id,
                Subscription.status.in_(statuses),
                Subscription.ends_at > now,
            )
            .order_by(Subscription.ends_at.desc())
            .limit(1)
        )
        if exclude is not None:
            stmt = stmt.where(Subscription.id != exclude)
        latest_end = await self.session.scalar(stmt)
        return latest_end if latest_end and latest_end > now else now

    async def activate(
        self,
        *,
        subscription_id: uuid.UUID,
        granted_by: CurrentUser | uuid.UUID,
        payment_ref: str | None = None,
    ) -> Subscription:
        """تأیید پرداخت و فعال‌سازی — پشتیبانی یا مدیر."""
        subscription = await self.session.get(Subscription, subscription_id)
        if subscription is None:
            raise NotFound("این اشتراک پیدا نشد.")
        if subscription.status == "ACTIVE":
            return subscription  # بی‌اثر در تکرار.
        if subscription.status in ("EXPIRED", "CANCELLED"):
            raise ValidationFailed("اشتراک منقضی یا لغوشده دوباره فعال نمی‌شود.")

        await self._activate_row(
            subscription,
            actor=granted_by,
            payment_ref=payment_ref,
            action=audit.SUBSCRIPTION_ACTIVATED,
        )
        await self.session.commit()
        return subscription

    async def grant(
        self,
        *,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        granted_by: CurrentUser | uuid.UUID,
        course_id: uuid.UUID | None = None,
        payment_ref: str | None = None,
        note: str | None = None,
    ) -> Subscription:
        """ساخت و فعال‌سازی در **یک تراکنش** — برای فیش دستی و اشتراک هدیه.

        پیش از ADR-0019 این دو commit جدا بود: اگر فعال‌سازی شکست می‌خورد،
        یک درخواست «در انتظار» بی‌صاحب در صف پشتیبانی می‌ماند.
        """
        subscription, _plan = await self._new_row(
            user_id=user_id, plan_id=plan_id, course_id=course_id, note=note
        )
        await self._activate_row(
            subscription,
            actor=granted_by,
            payment_ref=payment_ref,
            action=audit.SUBSCRIPTION_GRANTED,
        )
        await self.session.commit()
        return subscription

    async def _activate_row(
        self,
        subscription: Subscription,
        *,
        actor: CurrentUser | uuid.UUID,
        payment_ref: str | None,
        action: str,
    ) -> None:
        """دوره از **لحظهٔ تأیید** شمرده می‌شود، نه از لحظهٔ درخواست (ADR-0019).

        درخواستی که ده روز در صف ماند، اگر از روز درخواست شمرده می‌شد، ده
        روز از دورهٔ پرداخت‌شده را پیش از باز شدن می‌سوزاند. دورهٔ تازه
        پس از اشتراک **فعال** هم‌دامنه شروع می‌شود؛ درخواست‌های در انتظار
        دیگر حساب نمی‌شوند چون هنوز پولشان تأیید نشده.
        """
        plan = await self.session.get(SubscriptionPlan, subscription.plan_id)
        if plan is None:  # pragma: no cover — کلید خارجی تضمینش می‌کند
            raise NotFound("طرح این اشتراک پیدا نشد.")
        before = {
            "status": subscription.status,
            "starts_at": subscription.starts_at,
            "ends_at": subscription.ends_at,
        }
        starts_at = await self._next_start(
            subscription.user_id,
            subscription.course_id,
            statuses=("ACTIVE",),
            exclude=subscription.id,
        )
        subscription.starts_at = starts_at
        subscription.ends_at = starts_at + timedelta(days=plan.duration_days)
        subscription.status = "ACTIVE"
        subscription.granted_by = actor.id if isinstance(actor, CurrentUser) else actor
        subscription.payment_ref = payment_ref
        AuditService(self.session).stage(
            action,
            actor=actor,
            entity_type="SUBSCRIPTION",
            entity_id=subscription.id,
            before=before if action == audit.SUBSCRIPTION_ACTIVATED else None,
            after={
                "user_id": subscription.user_id,
                "plan": plan.code,
                "course_id": subscription.course_id,
                "status": "ACTIVE",
                "starts_at": subscription.starts_at,
                "ends_at": subscription.ends_at,
                "payment_ref": payment_ref,
                "amount_irr": subscription.amount_irr,
            },
        )
        await events.publish(
            self.session, events.SubscriptionActivated(subscription_id=subscription.id)
        )
        log.info(
            "subscription_activated",
            subscription_id=str(subscription.id),
            ends_at=subscription.ends_at.isoformat(),
        )

    async def reject(
        self, *, subscription_id: uuid.UUID, actor: CurrentUser | uuid.UUID, reason: str
    ) -> Subscription:
        """رد درخواست در انتظار — مثلاً فیش نامعتبر. دلیل به کاربر گفته می‌شود."""
        cleaned = reason.strip()
        if len(cleaned) < MIN_REJECT_REASON:
            raise ValidationFailed("دلیل رد را بنویس — کاربر آن را در اعلان می‌بیند.")
        subscription = await self.session.get(Subscription, subscription_id)
        if subscription is None:
            raise NotFound("این اشتراک پیدا نشد.")
        if subscription.status != "PENDING":
            raise Conflict("فقط درخواست در انتظار رد می‌شود.", code="SUBSCRIPTION_NOT_PENDING")
        subscription.status = "CANCELLED"
        subscription.cancelled_at = _now()
        AuditService(self.session).stage(
            audit.SUBSCRIPTION_REJECTED,
            actor=actor,
            entity_type="SUBSCRIPTION",
            entity_id=subscription.id,
            before={"status": "PENDING"},
            after={"status": "CANCELLED", "reason": cleaned, "user_id": subscription.user_id},
        )
        await events.publish(
            self.session,
            events.SubscriptionRejected(subscription_id=subscription.id, reason=cleaned),
        )
        await self.session.commit()
        return subscription

    async def cancel(self, *, subscription_id: uuid.UUID, user_id: uuid.UUID) -> Subscription:
        subscription = await self.session.get(Subscription, subscription_id)
        if subscription is None or subscription.user_id != user_id:
            # §6.4 قاعدهٔ ۴ — اشتراک کس دیگر برای این کاربر وجود ندارد.
            raise NotFound("این اشتراک پیدا نشد.")
        if subscription.status == "CANCELLED":
            return subscription
        subscription.status = "CANCELLED"
        subscription.cancelled_at = _now()
        await self.session.commit()
        return subscription

    async def mine(self, user_id: uuid.UUID) -> list[Subscription]:
        rows = await self.session.scalars(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(rows)

    async def expire_due(self, *, now: datetime | None = None) -> int:
        """اشتراک‌های گذشته را `EXPIRED` می‌کند — کار پس‌زمینهٔ روزانه.

        سنجش دسترسی به این کار وابسته **نیست** (خودش `ends_at` را
        می‌بیند)؛ این فقط گزارش و فهرست کاربر را تمیز نگه می‌دارد.
        """
        moment = now or _now()
        rows = list(
            await self.session.scalars(
                select(Subscription).where(
                    Subscription.status == "ACTIVE", Subscription.ends_at <= moment
                )
            )
        )
        for subscription in rows:
            subscription.status = "EXPIRED"
        if rows:
            await self.session.commit()
            log.info("subscriptions_expired", count=len(rows))
        return len(rows)


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = ["SubscriptionService"]
