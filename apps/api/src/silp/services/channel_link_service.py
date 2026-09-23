"""پیوند حساب تلگرام و ایتا — FR-MSG-02، M6-06، ADR-0013.

پیامک و ایمیل نشانی‌شان را از حساب کاربر دارند. پیام‌رسان‌ها نه: ربات
فقط به گفت‌وگویی می‌تواند پیام بدهد که شناسه‌اش را بداند. دو راه، چون
دو سکو دو توانایی متفاوت دارند:

* **تلگرام — پیوند عمیق.** `t.me/<bot>?start=<token>`؛ وب‌هوک ربات شناسهٔ
  گفت‌وگو را می‌گیرد. ربات تلگرام پیام دریافت می‌کند.
* **ایتا — کد تأیید.** کاربر شناسه‌اش را می‌دهد، کد به آن فرستاده و در
  سامانه وارد می‌شود. ایتایار فقط می‌فرستد و دریافت ندارد.

در هر دو، **مالکیت اثبات می‌شود** پیش از اینکه اعلانی آنجا برود: کسی
نمی‌تواند شناسهٔ ایتای دیگری را وارد کند و اعلان‌هایش را برای او بفرستد.

توکن پیوند عمیق با sha256 ذخیره می‌شود (با چکیده جست‌وجو می‌شود و ۹۶
بیت آنتروپی دارد)؛ کد شش‌رقمی ایتا با bcrypt و سقف تلاش، مثل OTP.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.config import Settings, get_settings
from silp.core.exceptions import Conflict, NotFound, RateLimited, ValidationFailed
from silp.core.logging import get_logger
from silp.core.security import generate_otp, hash_otp, verify_otp
from silp.domain.notifications import catalog
from silp.domain.notifications.catalog import Channel
from silp.integrations.messaging import enabled_channels
from silp.models.messaging import UserChannel
from silp.services.notification_service import NotificationService

log = get_logger("silp.channels")

LINK_TTL = timedelta(minutes=15)
CODE_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5
#: سه درخواست پیوند در ۱۰ دقیقه — هر درخواست ایتا یک پیام به نشانی
#: دلخواه کاربر می‌فرستد؛ بدون سقف، ابزار مزاحمت می‌شد.
LINK_LIMIT = ratelimit.Limit("channel:link", count=3, window_seconds=600)
#: شناسهٔ ایتا: عددی (شناسهٔ گفت‌وگو) یا @نام‌کاربری.
EITAA_ADDRESS = re.compile(r"^(?:-?\d{5,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")

LINK_FLOW: dict[str, str] = {"TELEGRAM": "DEEP_LINK", "EITAA": "CODE"}


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LinkStart:
    channel: str
    flow: str
    expires_at: datetime
    deep_link: str | None = None


class ChannelLinkService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def links(self, user_id: uuid.UUID) -> dict[str, UserChannel]:
        rows = await self.session.scalars(select(UserChannel).where(UserChannel.user_id == user_id))
        return {row.channel: row for row in rows}

    async def start(
        self, user_id: uuid.UUID, channel: str, *, address: str | None = None
    ) -> LinkStart:
        linkable = self._require_linkable(channel)
        limit = await ratelimit.check(LINK_LIMIT, str(user_id))
        if not limit.allowed:
            raise RateLimited(retry_after=limit.retry_after)
        if linkable == "TELEGRAM":
            return await self._start_telegram(user_id)
        return await self._start_code(user_id, linkable, address)

    async def _start_telegram(self, user_id: uuid.UUID) -> LinkStart:
        if not self.settings.telegram_bot_username:
            raise Conflict("ربات تلگرام سامانه هنوز پیکربندی نشده است.")
        token = secrets.token_urlsafe(12)
        expires = _now() + LINK_TTL
        row = await self._row(user_id, "TELEGRAM")
        row.link_code_hash = _sha256(token)
        row.link_expires_at = expires
        row.link_attempts = 0
        await self.session.commit()
        bot = self.settings.telegram_bot_username.lstrip("@")
        return LinkStart(
            channel="TELEGRAM",
            flow="DEEP_LINK",
            expires_at=expires,
            deep_link=f"https://t.me/{bot}?start={token}",
        )

    async def _start_code(
        self, user_id: uuid.UUID, channel: Channel, address: str | None
    ) -> LinkStart:
        cleaned = (address or "").strip()
        if not EITAA_ADDRESS.match(cleaned):
            raise ValidationFailed(
                "شناسهٔ ایتا را درست وارد کن: شناسهٔ عددی یا نام کاربری با @.",
                details={"fields": {"address": "شناسهٔ ایتا معتبر نیست."}},
            )
        await self._ensure_address_free(channel, cleaned, user_id)
        code = generate_otp(6)
        expires = _now() + CODE_TTL
        row = await self._row(user_id, channel)
        if row.address != cleaned:
            # نشانی تازه یعنی پیوند قبلی دیگر اثبات‌شده نیست.
            row.address = cleaned
            row.verified_at = None
        row.link_code_hash = hash_otp(code)
        row.link_expires_at = expires
        row.link_attempts = 0
        await NotificationService(self.session, self.settings).enqueue_direct(
            template="CHANNEL_VERIFY",
            channel=channel,
            recipient=cleaned,
            values={"code": code},
            user_id=user_id,
        )
        await self.session.commit()
        return LinkStart(channel=channel, flow="CODE", expires_at=expires)

    async def confirm(self, user_id: uuid.UUID, channel: str, code: str) -> UserChannel:
        linkable = self._require_linkable(channel)
        if LINK_FLOW[linkable] != "CODE":
            raise Conflict("این کانال با پیوند مستقیم وصل می‌شود، نه با کد.")
        row = await self.session.get(UserChannel, (user_id, linkable), with_for_update=True)
        if row is None or row.link_code_hash is None or row.link_expires_at is None:
            raise NotFound("درخواست اتصالی در جریان نیست. دوباره کد بگیر.")
        if row.link_expires_at <= _now():
            raise ValidationFailed("کد منقضی شده است. دوباره کد بگیر.", code="LINK_CODE_EXPIRED")
        if row.link_attempts >= MAX_CODE_ATTEMPTS:
            raise ValidationFailed(
                "تعداد تلاش‌ها زیاد بود. دوباره کد بگیر.", code="LINK_CODE_LOCKED"
            )
        if not verify_otp(code.strip(), row.link_code_hash):
            row.link_attempts += 1
            await self.session.commit()
            raise ValidationFailed("کد درست نیست.", code="LINK_CODE_INVALID")
        assert row.address is not None  # نشانی پیش از کد ثبت شده است
        await self._verify(row, row.address)
        return row

    async def bind_telegram(self, *, chat_id: str, token: str) -> UserChannel | None:
        """وب‌هوک تلگرام — `/start <token>`. توکن نامعتبر ⇒ None، نه خطا.

        ربات به هر پیامی پاسخ ۲۰۰ می‌دهد؛ خطا فقط باعث می‌شد تلگرام همان
        به‌روزرسانی را بارها دوباره بفرستد.
        """
        row = await self.session.scalar(
            select(UserChannel)
            .where(
                UserChannel.channel == "TELEGRAM",
                UserChannel.link_code_hash == _sha256(token),
            )
            .with_for_update()
        )
        if row is None or row.link_expires_at is None or row.link_expires_at <= _now():
            return None
        # همان گفت‌وگو قبلاً به حساب دیگری وصل بوده: صاحب گفت‌وگو الان
        # ثابت کرد مالک این حساب هم هست، پس پیوند قبلی آزاد می‌شود.
        await self.session.execute(
            update(UserChannel)
            .where(
                UserChannel.channel == "TELEGRAM",
                UserChannel.address == chat_id,
                UserChannel.user_id != row.user_id,
            )
            .values(address=None, verified_at=None)
        )
        await self._verify(row, chat_id)
        return row

    async def unlink(self, user_id: uuid.UUID, channel: str) -> None:
        linkable = self._require_linkable(channel, require_enabled=False)
        row = await self.session.get(UserChannel, (user_id, linkable))
        if row is not None:
            await self.session.delete(row)
            await self.session.commit()

    # ── درونی ──────────────────────────────────────────────────────────
    async def _verify(self, row: UserChannel, address: str) -> None:
        row.address = address
        row.verified_at = _now()
        row.link_code_hash = None
        row.link_expires_at = None
        row.link_attempts = 0
        await self.session.flush()
        notifications = NotificationService(self.session, self.settings)
        channel: Channel = row.channel  # type: ignore[assignment]
        await notifications.add_channel_everywhere(row.user_id, channel)
        await notifications.notify(
            "CHANNEL_LINKED",
            [row.user_id],
            {"channel": catalog.CHANNEL_TITLE_FA[channel]},
            action_url="/me/settings",
            force_channels=(channel,),
        )
        await self.session.commit()
        log.info("channel_linked", user_id=str(row.user_id), channel=row.channel)

    async def _row(self, user_id: uuid.UUID, channel: str) -> UserChannel:
        row = await self.session.get(UserChannel, (user_id, channel), with_for_update=True)
        if row is None:
            row = UserChannel(user_id=user_id, channel=channel, link_attempts=0)
            self.session.add(row)
        return row

    async def _ensure_address_free(self, channel: str, address: str, user_id: uuid.UUID) -> None:
        taken = await self.session.scalar(
            select(UserChannel.user_id).where(
                UserChannel.channel == channel,
                UserChannel.address == address,
                UserChannel.verified_at.is_not(None),
                UserChannel.user_id != user_id,
            )
        )
        if taken is not None:
            raise Conflict("این حساب پیام‌رسان به کاربر دیگری وصل است.")

    def _require_linkable(self, channel: str, *, require_enabled: bool = True) -> Channel:
        if channel not in catalog.LINKABLE_CHANNELS:
            raise NotFound("این کانال قابل اتصال نیست.")
        if require_enabled and channel not in enabled_channels(self.settings):
            raise Conflict("این کانال در سامانه فعال نیست.")
        return channel


__all__ = ["LINK_FLOW", "ChannelLinkService", "LinkStart"]
