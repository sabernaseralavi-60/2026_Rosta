"""کارگر صف ارسال — §7.10، M6-03.

```
تراکنش ۱: SELECT … FOR UPDATE SKIP LOCKED LIMIT 50
          status = SENDING، attempts += 1، اجاره = now + ۵ دقیقه
          COMMIT
بیرون از تراکنش: ارسال هم‌زمان به آداپتورها (D-08)
تراکنش ۲: SENT | FAILED با عقب‌نشینی | DEAD — فقط اگر اجاره هنوز مال ماست
```

## چرا اجاره

اگر ارسال داخل تراکنش ۱ بود، یک پیامک کند کاوه‌نگار قفل سطر را ده ثانیه
نگه می‌داشت و D-08 را می‌شکست. اگر `SENDING` اجاره نداشت، کارگری که وسط
ارسال بمیرد، پیام را برای همیشه در `SENDING` جا می‌گذاشت. پس
`next_attempt_at` در `SENDING` یعنی «پایان اجاره»؛ پس از آن پیام دوباره
برداشته می‌شود. تراکنش ۲ فقط ردیفی را می‌نویسد که `attempts` آن هنوز همان
است که برداشتیم — نتیجهٔ کارگر کندی که اجاره‌اش تمام شده، نتیجهٔ کارگر
بعدی را بازنویسی نمی‌کند.

این یعنی تحویل «حداقل یک بار» است، نه «دقیقاً یک بار»: کارگری که پیام را
فرستاد و پیش از تراکنش ۲ مُرد، باعث ارسال دوباره می‌شود. برای اعلان این
پذیرفتنی است؛ پیام گم‌شده بدتر از پیام تکراری است.

## شکست یک کانال

هر پیام ردیف مستقل خودش است و هر آداپتور شکست را برمی‌گرداند، نه
استثنا. تلگرامِ فیلترشده پیام‌های خودش را `FAILED` می‌کند و پیامک‌های
همان دسته بی‌اثر می‌روند (FR-MSG-02).
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings, get_settings
from silp.core.exceptions import Conflict, NotFound
from silp.core.logging import get_logger
from silp.core.permissions import Role
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.notifications import schedule
from silp.domain.notifications.push import endpoint_of
from silp.domain.notifications.templating import Rendered, TemplateError, render
from silp.domain.text import to_persian_digits
from silp.integrations.messaging import ChannelSender, OutgoingMessage, SendResult, channel_sender
from silp.models.identity import UserRole
from silp.models.messaging import (
    DISPATCHABLE_STATUSES,
    OUTBOX_STATUSES,
    OutboxMessage,
    PushSubscription,
)
from silp.services.notification_service import NotificationService

log = get_logger("silp.outbox")

MAX_ERROR_LENGTH = 500
REVOKED_ERROR = "اشتراک Push لغو شده است."
SIGNATURE = "— سامانهٔ سابِر"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class DispatchStats:
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0
    #: اشتراک Push لغوشده — جدا از `dead` تا هشدار مدیر را برنینگیزد.
    revoked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "dead": self.dead,
            "revoked": self.revoked,
        }


@dataclass
class _Job:
    id: uuid.UUID
    attempts: int
    priority: str
    channel: str
    message: OutgoingMessage | None = None
    error: str | None = None
    result: SendResult | None = field(default=None)


class OutboxService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        senders: Mapping[str, ChannelSender | None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.notifications = NotificationService(session, self.settings)
        self._senders: dict[str, ChannelSender | None] = dict(senders or {})
        self._rng = rng

    # ── ارسال ──────────────────────────────────────────────────────────
    async def dispatch(
        self, *, limit: int | None = None, now: datetime | None = None
    ) -> DispatchStats:
        moment = now or _now()
        jobs = await self._claim(limit or self.settings.outbox_batch_size, moment)
        stats = DispatchStats(claimed=len(jobs))
        if not jobs:
            return stats

        gate = asyncio.Semaphore(self.settings.outbox_concurrency)

        async def run(job: _Job) -> None:
            if job.message is None:
                return
            sender = self._sender(job.channel)
            if sender is None:
                job.result = SendResult(
                    delivered=False, error="این کانال در سامانه خاموش است.", permanent=True
                )
                return
            async with gate:
                try:
                    job.result = await sender.send(job.message)
                except Exception as exc:
                    log.exception("channel_sender_crashed", channel=job.channel)
                    job.result = SendResult(delivered=False, error=f"{type(exc).__name__}")

        await asyncio.gather(*(run(job) for job in jobs))
        await self._record(jobs, stats)
        if stats.sent or stats.failed or stats.dead or stats.revoked:
            log.info("outbox_dispatched", **stats.as_dict())
        return stats

    async def _claim(self, limit: int, now: datetime) -> list[_Job]:
        rows = list(
            await self.session.scalars(
                select(OutboxMessage)
                .where(
                    OutboxMessage.status.in_(DISPATCHABLE_STATUSES),
                    OutboxMessage.next_attempt_at <= now,
                )
                .order_by(OutboxMessage.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        jobs: list[_Job] = []
        for row in rows:
            row.status = "SENDING"
            row.attempts += 1
            row.next_attempt_at = now + schedule.LEASE
            job = _Job(id=row.id, attempts=row.attempts, priority=row.priority, channel=row.channel)
            try:
                rendered = await self.render(row)
            except TemplateError as exc:
                job.error = str(exc)
            else:
                job.message = OutgoingMessage(
                    channel=row.channel,
                    recipient=row.recipient,
                    subject=rendered.subject,
                    body=rendered.body,
                    link=str((row.payload or {}).get("values", {}).get("link") or "") or None,
                    priority=row.priority,
                )
            jobs.append(job)
        await self.session.commit()
        return jobs

    async def _record(self, jobs: list[_Job], stats: DispatchStats) -> None:
        now = _now()
        for job in jobs:
            result = job.result or SendResult(
                delivered=False, error=job.error or "پیام ساخته نشد.", permanent=True
            )
            owned = (
                OutboxMessage.id == job.id,
                OutboxMessage.status == "SENDING",
                OutboxMessage.attempts == job.attempts,
            )
            if result.delivered:
                values: dict[str, object] = {
                    "status": "SENT",
                    "sent_at": now,
                    "provider_message_id": result.provider_message_id,
                    "last_error": None,
                }
                stats.sent += 1
            elif result.revoked:
                # اشتراک Push لغو شده — رفت‌وآمد عادی مرورگرهاست، نه خرابی؛ مدیر
                # را بیدار نمی‌کند (`_alert_admins` این خطا را نمی‌شمارد).
                values = {"status": "DEAD", "last_error": REVOKED_ERROR}
                stats.revoked += 1
                await self._forget_subscription(job)
            elif result.permanent or schedule.is_exhausted(job.attempts):
                values = {"status": "DEAD", "last_error": _clip(result.error)}
                stats.dead += 1
            else:
                retry_at = now + schedule.retry_delay(job.attempts, rng=self._rng)
                values = {
                    "status": "FAILED",
                    "last_error": _clip(result.error),
                    "next_attempt_at": self.notifications.first_attempt_at(retry_at, job.priority),
                }
                stats.failed += 1
            await self.session.execute(update(OutboxMessage).where(*owned).values(**values))
        if stats.dead:
            await self._alert_admins(now)
        await self.session.commit()

    async def _forget_subscription(self, job: _Job) -> None:
        endpoint = endpoint_of(job.message.recipient) if job.message else None
        if endpoint is not None:
            await self.session.execute(
                delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )

    def _sender(self, channel: str) -> ChannelSender | None:
        if channel not in self._senders:
            self._senders[channel] = channel_sender(self.settings, channel)
        return self._senders[channel]

    # ── رندر ───────────────────────────────────────────────────────────
    async def render(self, message: OutboxMessage) -> Rendered:
        """الگوی اختصاصی کانال؛ اگر نبود، الگوی داخلی به‌علاوهٔ لینک.

        رندر هنگام ارسال است، نه هنگام صف کردن: اگر مدیر غلط املایی
        پیامکی را اصلاح کند، پیام‌هایی که هنوز در صف‌اند یا `DEAD` شده و
        دوباره تلاش می‌شوند، متن درست را می‌برند.
        """
        values = dict((message.payload or {}).get("values") or {})
        own = await self.notifications.template(message.template, message.channel)
        if own is not None:
            return render(own.subject, own.body, values)
        base = await self.notifications.template(message.template, "IN_APP")
        if base is None:
            raise TemplateError(
                f"الگوی «{message.template}» برای کانال {message.channel} تعریف نشده است."
            )
        inner = render(base.subject, base.body, values)
        return _wrap(message.channel, inner, values)

    # ── هشدار به مدیر — §7.10 «DEAD ⇒ هشدار به مدیر» ────────────────────
    async def _alert_admins(self, now: datetime) -> None:
        admins = list(
            await self.session.scalars(
                select(UserRole.user_id).where(UserRole.role_code == Role.ADMIN.value).distinct()
            )
        )
        if not admins:
            return
        dead = await self.session.scalar(
            select(func.count())
            .select_from(OutboxMessage)
            .where(
                OutboxMessage.status == "DEAD",
                OutboxMessage.created_at >= now - timedelta(days=1),
                func.coalesce(OutboxMessage.last_error, "") != REVOKED_ERROR,
            )
        )

        # یک هشدار در روز، نه یکی برای هر پیام — قطعی کاوه‌نگار نباید صندوق
        # مدیر را با صد اعلان پر کند.
        day = now.astimezone(LOCAL_TZ).date().isoformat()
        await self.notifications.notify(
            "OUTBOX_DEAD",
            admins,
            {"count": to_persian_digits(int(dead or 0))},
            action_url="/admin/notifications",
            dedup_key=f"OUTBOX_DEAD:{day}",
        )

    # ── مدیریت — /admin/outbox ─────────────────────────────────────────
    async def listing(
        self,
        *,
        status: str | None = None,
        channel: str | None = None,
        user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OutboxMessage], int]:
        query = select(OutboxMessage)
        if status is not None:
            query = query.where(OutboxMessage.status == status)
        if channel is not None:
            query = query.where(OutboxMessage.channel == channel)
        if user_id is not None:
            query = query.where(OutboxMessage.user_id == user_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(OutboxMessage.created_at.desc(), OutboxMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(OutboxMessage.status, func.count()).group_by(OutboxMessage.status)
        )
        counts = {status: 0 for status in OUTBOX_STATUSES}
        counts.update({status: int(n) for status, n in rows.all()})
        return counts

    async def retry(self, message_id: uuid.UUID) -> OutboxMessage:
        """§7.10 — «پیام DEAD به‌صورت دستی قابل تلاش مجدد است»."""
        message = await self.session.get(OutboxMessage, message_id, with_for_update=True)
        if message is None:
            raise NotFound("این پیام پیدا نشد.")
        if message.status not in ("DEAD", "FAILED"):
            raise Conflict("فقط پیام ناموفق یا ارسال‌نشده دوباره فرستاده می‌شود.")
        message.status = "QUEUED"
        message.attempts = 0
        message.next_attempt_at = _now()
        await self.session.commit()
        log.info("outbox_retried", message_id=str(message_id))
        return message

    async def retry_all_dead(self, *, channel: str | None = None) -> int:
        """پس از رفع قطعی (مثلاً شارژ کاوه‌نگار): همهٔ DEADها به صف برمی‌گردند."""
        conditions = [OutboxMessage.status == "DEAD"]
        if channel is not None:
            conditions.append(OutboxMessage.channel == channel)
        result = await self.session.execute(
            update(OutboxMessage)
            .where(*conditions)
            .values(status="QUEUED", attempts=0, next_attempt_at=_now())
        )
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


def _wrap(channel: str, inner: Rendered, values: Mapping[str, object]) -> Rendered:
    """پیام بیرونی از روی الگوی داخلی — وقتی کانال الگوی خودش را ندارد."""
    link = str(values.get("link") or "")
    if channel == "SMS":
        return Rendered(subject=None, body=inner.body)
    if channel == "PUSH":
        # لینک از `OutgoingMessage.link` می‌رود و با لمس اعلان باز می‌شود؛ در متن نمی‌آید.
        return Rendered(subject=inner.subject, body=inner.body)
    if channel == "EMAIL":
        name = str(values.get("name") or "").strip()
        parts = [f"سلام {name}،" if name else "سلام،", inner.body]
        if link:
            parts.append(link)
        parts.append(SIGNATURE)
        return Rendered(subject=inner.subject, body="\n\n".join(parts))
    body = f"{inner.body}\n\n{link}" if link else inner.body
    return Rendered(subject=inner.subject, body=body)


def _clip(error: str | None) -> str | None:
    if error is None:
        return None
    return error[:MAX_ERROR_LENGTH]


__all__ = ["DispatchStats", "OutboxService"]
