"""ثبت «مسئله / نیاز» و «درخواست همکاری» از بازدیدکننده — ADR-0030.

* **بی‌حساب:** فرم نیاز به ورود ندارد؛ راه تماس کافی است.
* **وصل‌شدن به فرد:** اگر شمارهٔ تأییدشدهٔ (یا ایمیل تأییدشدهٔ) یک کاربر با تماس یکی
  باشد، درخواست به همان فرد وصل می‌شود و کد شخصی‌اش برمی‌گردد. تأییدنشده کافی
  نیست: هر کسی می‌تواند شمارهٔ دیگری را تایپ کند و به نام او درخواست بگذارد.
* **سهمیه:** ۵ درخواست در ساعت به‌ازای IP و ۳ در ساعت به‌ازای هر راه تماس.
* commit صریح در همین لایه است (قرارداد `db/session.py`).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.exceptions import RateLimited
from silp.core.logging import get_logger
from silp.models.identity import User
from silp.models.intake import IntakeRequest
from silp.schemas.intake import CollaborationIn, IntakeIn

log = get_logger(__name__)

IP_LIMIT = ratelimit.Limit("public:intake:ip", count=5, window_seconds=3600)
CONTACT_LIMIT = ratelimit.Limit("public:intake:contact", count=3, window_seconds=3600)

PREFIX = {"INTAKE": "Q", "COLLABORATION": "C"}
#: بدنهٔ کارت‌های «تله» که ربات پر کرده: چیزی ذخیره نمی‌شود، پاسخ ظاهراً موفق است.
DECOY_CODE = "Q-0000"


class IntakeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def submit_intake(
        self, data: IntakeIn, *, ip: str
    ) -> tuple[IntakeRequest | None, str | None]:
        payload: dict[str, Any] = {
            key: value
            for key, value in {
                "expected_result": data.expected_result,
                "sector": data.sector,
                "has_data": data.has_data,
                "timeline": data.timeline,
                "budget": data.budget,
                "notes": data.notes,
            }.items()
            if value
        }
        return await self._store(
            data,
            kind="INTAKE",
            summary=data.summary,
            need_type=data.need_type,
            services=list(data.services),
            payload=payload,
            ip=ip,
        )

    async def submit_collaboration(
        self, data: CollaborationIn, *, ip: str
    ) -> tuple[IntakeRequest | None, str | None]:
        payload: dict[str, Any] = {
            key: value
            for key, value in {
                "specialty": data.specialty,
                "skills": data.skills,
                "experience": data.experience,
                "interests": data.interests,
                "ways": list(data.ways),
                "hours_per_week": data.hours_per_week,
                "portfolio_url": data.portfolio_url,
            }.items()
            if value
        }
        return await self._store(
            data,
            kind="COLLABORATION",
            summary=data.intro,
            need_type="Collaboration",
            services=[],
            payload=payload,
            ip=ip,
        )

    async def _store(
        self,
        data: IntakeIn | CollaborationIn,
        *,
        kind: str,
        summary: str,
        need_type: str,
        services: list[str],
        payload: dict[str, Any],
        ip: str,
    ) -> tuple[IntakeRequest | None, str | None]:
        if data.website:
            log.info("intake_decoy_hit", kind=kind)
            return None, None
        await self._enforce_limits(data.mobile or data.email or "", ip)

        user = await self._match_user(data.mobile, data.email)
        number = int(await self.session.scalar(text("SELECT nextval('intake_code_seq')")) or 0)
        request = IntakeRequest(
            kind=kind,
            tracking_code=f"{PREFIX[kind]}-{number}",
            user_id=user.id if user else None,
            contact_name=data.name,
            contact_mobile=data.mobile,
            contact_email=data.email,
            organization=data.organization,
            need_type=need_type,
            services=services,
            summary=summary,
            payload=payload,
        )
        self.session.add(request)
        await self.session.commit()
        log.info("intake_submitted", kind=kind, code=request.tracking_code, matched=bool(user))
        return request, user.person_code if user else None

    async def _enforce_limits(self, contact: str, ip: str) -> None:
        for limit, identity in ((IP_LIMIT, ip), (CONTACT_LIMIT, contact)):
            result = await ratelimit.check(limit, identity)
            if not result.allowed:
                raise RateLimited(retry_after=result.retry_after)

    async def _match_user(self, mobile: str | None, email: str | None) -> User | None:
        conditions = []
        if mobile:
            conditions.append((User.mobile == mobile) & User.mobile_verified_at.is_not(None))
        if email:
            conditions.append((User.email == email) & User.email_verified_at.is_not(None))
        if not conditions:
            return None
        result = await self.session.scalars(
            select(User).where(User.deleted_at.is_(None), or_(*conditions)).limit(1)
        )
        return result.first()


__all__ = ["DECOY_CODE", "IntakeService"]
