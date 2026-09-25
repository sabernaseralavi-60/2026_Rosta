"""اشتراک Push وب — ADR-0029، FR-MSG-02.

هر مرورگر یک اشتراک دارد (`endpoint` یکتا). مرورگری که کاربر دیگری وارد
آن می‌شود، اشتراک را به مالک تازه منتقل می‌کند: اعلان کاربر قبلی نباید روی
دستگاهی که دیگر مال او نیست پدیدار شود.

نقطهٔ پایانی را کاربر می‌دهد و سرور به آن `POST` می‌زند؛ پس فقط میزبان‌های
فهرست مجاز پذیرفته می‌شوند (`domain.notifications.push`).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings, get_settings
from silp.core.exceptions import ValidationFailed
from silp.core.logging import get_logger
from silp.domain.notifications import push
from silp.integrations.messaging import enabled_channels
from silp.models.messaging import PushSubscription
from silp.services.notification_service import NotificationService

log = get_logger("silp.push")


class PushService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return "PUSH" in enabled_channels(self.settings)

    async def count(self, user_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.user_id == user_id)
        )
        return int(total or 0)

    async def subscribe(
        self,
        user_id: uuid.UUID,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str | None = None,
    ) -> int:
        """اشتراک این دستگاه را ثبت یا نو می‌کند. خروجی: شمار دستگاه‌های کاربر."""
        if not self.enabled():
            raise ValidationFailed("اعلان مرورگر در این سامانه فعال نیست.")
        reason = push.check_endpoint(endpoint, push.allowed_hosts(self.settings.push_allowed_hosts))
        if reason is not None:
            raise ValidationFailed(reason)
        if not (p256dh and auth) or max(len(p256dh), len(auth)) > push.MAX_KEY_LENGTH:
            raise ValidationFailed("کلیدهای اشتراک معتبر نیستند.")

        had_any = await self.count(user_id) > 0
        statement = insert(PushSubscription).values(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=(user_agent or "")[:300] or None,
        )
        # همان مرورگر با حساب دیگر: مالک عوض می‌شود، ردیف دوم ساخته نمی‌شود.
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["endpoint"],
                set_={
                    "user_id": statement.excluded.user_id,
                    "p256dh": statement.excluded.p256dh,
                    "auth": statement.excluded.auth,
                    "user_agent": statement.excluded.user_agent,
                },
            )
        )
        await self._trim(user_id)
        if not had_any:
            # مثل پیوند تلگرام: کاربری که Push را روشن کرد، انتظار دارد در همه
            # دسته‌ها بیاید؛ اگر خواست، برای یک دسته خاموشش می‌کند.
            await NotificationService(self.session, self.settings).add_channel_everywhere(
                user_id, "PUSH"
            )
        await self.session.commit()
        log.info("push_subscribed", user_id=str(user_id))
        return await self.count(user_id)

    async def unsubscribe(self, user_id: uuid.UUID, endpoint: str) -> int:
        """اشتراک این دستگاه را برمی‌دارد — فقط اگر مال همین کاربر باشد.

        اشتراکِ نبود یا مالِ دیگری بی‌صدا نادیده گرفته می‌شود: پاسخ نباید لو
        دهد که آن نقطهٔ پایانی در سامانه هست.
        """
        await self.session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
            )
        )
        await self.session.commit()
        return await self.count(user_id)

    async def _trim(self, user_id: uuid.UUID) -> None:
        keep = (
            select(PushSubscription.id)
            .where(PushSubscription.user_id == user_id)
            .order_by(PushSubscription.created_at.desc(), PushSubscription.id.desc())
            .limit(push.MAX_SUBSCRIPTIONS_PER_USER)
        )
        await self.session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.id.not_in(keep)
            )
        )


__all__ = ["PushService"]
