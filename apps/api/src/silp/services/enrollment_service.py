"""چرخهٔ ثبت‌نام در ارائه — FR-AUTH-05، §7.2، §5.5.

ثبت‌نام دو مسیر دارد و کدام‌یک اجرا می‌شود را **ارائه** تعیین می‌کند،
نه کاربر:

* `requires_approval = false` ⇒ وضعیت مستقیم `ACTIVE`.
* `requires_approval = true`  ⇒ وضعیت `PENDING` تا تصمیم استاد.

کد ثبت‌نام (`enrollment_code`) دروازهٔ جداگانه‌ای است و پیش از هر دو
بررسی می‌شود: ارائه‌ای که کد دارد، بدون کد ثبت‌نام نمی‌پذیرد.

**ظرفیت زیر هم‌زمانی:** شمارش و درج در یک تراکنش‌اند و ردیف ارائه با
`FOR UPDATE` قفل می‌شود. بدون آن، دو درخواست هم‌زمان روی آخرین صندلی
هر دو موفق می‌شوند.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    AlreadyEnrolled,
    EnrollmentCodeInvalid,
    NotFound,
    OfferingFull,
    OfferingNotOpen,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.models.education import CourseOffering, Enrollment

log = get_logger("silp.enrollment")

# وضعیت‌هایی که یک صندلی را اشغال می‌کنند.
SEAT_TAKING_STATUSES = ("PENDING", "ACTIVE", "COMPLETED")


class EnrollmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enroll(
        self,
        *,
        offering_id: uuid.UUID,
        student_id: uuid.UUID,
        enrollment_code: str | None = None,
    ) -> Enrollment:
        """ثبت‌نام دانشجو — §5.5 `POST /offerings/{id}/enroll`."""
        offering = await self._lock_offering(offering_id)

        if not offering.accepts_enrollment:
            raise OfferingNotOpen

        if offering.enrollment_code:
            given = (enrollment_code or "").strip()
            # مقایسه بدون حساسیت به حروف: کد را استاد روی تخته می‌نویسد،
            # نه یک سامانه که دقیق کپی کند.
            if given.casefold() != offering.enrollment_code.casefold():
                raise EnrollmentCodeInvalid

        existing = await self.session.scalar(
            select(Enrollment).where(
                Enrollment.offering_id == offering_id, Enrollment.student_id == student_id
            )
        )
        if existing is not None:
            if existing.status in SEAT_TAKING_STATUSES:
                raise AlreadyEnrolled
            # بازگشت پس از انصراف یا رد: همان ردیف زنده می‌شود، نه ردیف دوم
            # (قید یکتای (offering, student) اجازهٔ دوم را نمی‌دهد).
            existing.status = "ACTIVE" if not offering.requires_approval else "PENDING"
            existing.enrolled_at = _now()
            existing.decided_at = None
            existing.decided_by = None
            await self._assert_capacity(offering, exclude_enrollment_id=existing.id)
            await self.session.commit()
            log.info("enrollment_reactivated", offering_id=str(offering_id))
            return existing

        await self._assert_capacity(offering)

        enrollment = Enrollment(
            offering_id=offering_id,
            student_id=student_id,
            status="PENDING" if offering.requires_approval else "ACTIVE",
        )
        self.session.add(enrollment)
        await self.session.commit()
        log.info(
            "enrollment_created",
            offering_id=str(offering_id),
            status=enrollment.status,
        )
        return enrollment

    async def _lock_offering(self, offering_id: uuid.UUID) -> CourseOffering:
        offering = await self.session.scalar(
            select(CourseOffering)
            .where(CourseOffering.id == offering_id, CourseOffering.deleted_at.is_(None))
            .with_for_update()
        )
        if offering is None:
            raise NotFound("این ارائه پیدا نشد.")
        return offering

    async def _assert_capacity(
        self, offering: CourseOffering, *, exclude_enrollment_id: uuid.UUID | None = None
    ) -> None:
        if offering.capacity is None:
            return
        stmt = select(func.count()).where(
            Enrollment.offering_id == offering.id,
            Enrollment.status.in_(SEAT_TAKING_STATUSES),
        )
        if exclude_enrollment_id is not None:
            stmt = stmt.where(Enrollment.id != exclude_enrollment_id)
        taken = int(await self.session.scalar(stmt) or 0)
        if taken >= offering.capacity:
            raise OfferingFull

    async def drop(self, *, offering_id: uuid.UUID, student_id: uuid.UUID) -> Enrollment:
        """انصراف — §5.5 `DELETE /offerings/{id}/enroll`.

        درس تمام‌شده انصراف‌پذیر نیست: نمرهٔ ثبت‌شده با حذف ثبت‌نام
        بی‌صاحب می‌ماند.
        """
        enrollment = await self.session.scalar(
            select(Enrollment).where(
                Enrollment.offering_id == offering_id, Enrollment.student_id == student_id
            )
        )
        if enrollment is None:
            raise NotFound("ثبت‌نامی برای شما در این درس نیست.")
        if enrollment.status == "COMPLETED":
            raise ValidationFailed("درس تمام‌شده قابل انصراف نیست.")
        if enrollment.status == "DROPPED":
            return enrollment
        enrollment.status = "DROPPED"
        enrollment.decided_at = _now()
        await self.session.commit()
        log.info("enrollment_dropped", offering_id=str(offering_id))
        return enrollment

    async def decide(
        self,
        *,
        enrollment_id: uuid.UUID,
        approve: bool,
        decided_by: uuid.UUID,
    ) -> Enrollment:
        """تأیید یا رد ثبت‌نام — §5.5 `POST /teach/enrollments/{id}/decide`."""
        enrollment = await self.session.get(Enrollment, enrollment_id)
        if enrollment is None:
            raise NotFound("این درخواست ثبت‌نام پیدا نشد.")
        if enrollment.status != "PENDING":
            raise ValidationFailed("این درخواست قبلاً تصمیم‌گیری شده است.")

        if approve:
            offering = await self._lock_offering(enrollment.offering_id)
            await self._assert_capacity(offering, exclude_enrollment_id=enrollment.id)

        enrollment.status = "ACTIVE" if approve else "REJECTED"
        enrollment.decided_at = _now()
        enrollment.decided_by = decided_by
        await self.session.commit()
        log.info(
            "enrollment_decided",
            enrollment_id=str(enrollment_id),
            status=enrollment.status,
        )
        return enrollment

    async def roster(
        self, offering_id: uuid.UUID, *, status: str | None = None
    ) -> list[Enrollment]:
        stmt = select(Enrollment).where(Enrollment.offering_id == offering_id)
        if status:
            stmt = stmt.where(Enrollment.status == status)
        rows = await self.session.scalars(stmt.order_by(Enrollment.enrolled_at))
        return list(rows)

    async def set_final_grade(
        self, *, enrollment_id: uuid.UUID, grade: float, decided_by: uuid.UUID
    ) -> Enrollment:
        """ثبت نمرهٔ نهایی — FR-EDU/`PATCH /teach/enrollments/{id}/grade`.

        ثبت نمره درس را `COMPLETED` می‌کند: نمره یعنی درس تمام شده، و
        دانشجو دسترسی رایگانش به کتابخانه را نگه می‌دارد (ADR-0009).
        """
        enrollment = await self.session.get(Enrollment, enrollment_id)
        if enrollment is None:
            raise NotFound("این ثبت‌نام پیدا نشد.")
        if enrollment.status in ("DROPPED", "REJECTED"):
            raise ValidationFailed("برای ثبت‌نام لغوشده نمره ثبت نمی‌شود.")
        if not 0 <= grade <= 20:
            raise ValidationFailed("نمره باید بین ۰ تا ۲۰ باشد.")

        enrollment.final_grade = grade  # type: ignore[assignment]
        enrollment.status = "COMPLETED"
        enrollment.decided_at = _now()
        enrollment.decided_by = decided_by
        await self.session.commit()
        return enrollment


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = ["SEAT_TAKING_STATUSES", "EnrollmentService"]
