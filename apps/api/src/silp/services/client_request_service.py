"""داشبورد مشتری: درخواست‌های من و پیگیری بی‌ورود — ADR-0032.

دو در، دو سطح اعتماد:

* **واردشده** — درخواست‌های `user_id` خودش، به‌علاوهٔ آنچه با موبایل/ایمیلِ **تأییدشدهٔ** او
  ثبت شده و هنوز به حسابش وصل نشده (پیش از ثبت‌نام فرستاده بود). متن کامل را می‌بیند.
* **بی‌ورود** — کد پیگیری **و** راه تماسِ ثبت‌شده. هیچ متنی از درخواست برنمی‌گردد (فقط وضعیت
  و یادداشت‌های عمومی)، چون کد پیوسته است (`Q-1001`، `Q-1002`…) و شمارهٔ تماس شاید لو رفته
  باشد. هر ناموفقی یک `NotFound` یکسان است تا کد و راه تماس تشخیص‌داده نشود؛ سهمیه: ۱۰ در ساعت
  به‌ازای IP و ۵ در ساعت به‌ازای هر کد.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.exceptions import NotFound, RateLimited
from silp.domain.identity.normalize import normalize_email, normalize_mobile
from silp.models.identity import User
from silp.models.intake import IntakeEvent, IntakeRequest

IP_LIMIT = ratelimit.Limit("public:track:ip", count=10, window_seconds=3600)
CODE_LIMIT = ratelimit.Limit("public:track:code", count=5, window_seconds=3600)

Pair = tuple[IntakeRequest, list[IntakeEvent]]


class ClientRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _events(self, request_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[IntakeEvent]]:
        grouped: dict[uuid.UUID, list[IntakeEvent]] = {rid: [] for rid in request_ids}
        if not request_ids:
            return grouped
        rows = await self.session.scalars(
            select(IntakeEvent)
            .where(IntakeEvent.request_id.in_(request_ids))
            .order_by(IntakeEvent.id)
        )
        for event in rows:
            grouped[event.request_id].append(event)
        return grouped

    def _mine(self, user: User) -> list[object]:
        conditions: list[object] = [IntakeRequest.user_id == user.id]
        if user.mobile and user.mobile_verified_at is not None:
            conditions.append(IntakeRequest.contact_mobile == user.mobile)
        if user.email and user.email_verified_at is not None:
            conditions.append(IntakeRequest.contact_email == user.email)
        return conditions

    async def mine(self, user_id: uuid.UUID) -> list[Pair]:
        user = await self.session.get(User, user_id)
        if user is None:
            return []
        requests = list(
            await self.session.scalars(
                select(IntakeRequest)
                .where(or_(*self._mine(user)))  # type: ignore[arg-type]
                .order_by(IntakeRequest.created_at.desc(), IntakeRequest.id.desc())
            )
        )
        events = await self._events([r.id for r in requests])
        return [(r, events[r.id]) for r in requests]

    async def track(self, code: str, contact: str, *, ip: str) -> Pair:
        for limit, identity in ((IP_LIMIT, ip), (CODE_LIMIT, code)):
            result = await ratelimit.check(limit, identity)
            if not result.allowed:
                raise RateLimited(retry_after=result.retry_after)

        request = await self.session.scalar(
            select(IntakeRequest).where(IntakeRequest.tracking_code == code)
        )
        mobile, email = normalize_mobile(contact), normalize_email(contact)
        matches = request is not None and (
            (mobile is not None and request.contact_mobile == mobile)
            or (email is not None and request.contact_email == email)
        )
        if request is None or not matches:
            raise NotFound("درخواستی با این کد و راه تماس پیدا نشد.")
        events = await self._events([request.id])
        return request, events[request.id]


__all__ = ["ClientRequestService"]
