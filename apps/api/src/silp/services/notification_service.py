"""سرویس اعلان — FR-MSG-01/02، §7.10، M6-02.

## یک تراکنش، سه نوشتن (D-08)

`notify` در **همان نشست** رویداد دامنه اجرا می‌شود و فقط درج می‌کند:

۱. یک ردیف `notifications` برای هر گیرنده — مرکز اعلان.
۲. یک ردیف `outbox_messages` برای هر کانال بیرونی فعال همان گیرنده.
۳. نشانهٔ «بیدار شو» برای جریان SSE — که **پس از commit** فرستاده می‌شود.

هیچ فراخوانی شبکه‌ای اینجا نیست. اگر تراکنش برگردد، اعلان و پیام صف هم
برمی‌گردند؛ پس پیامکِ «تحویلت تأیید شد» برای تأییدی که ثبت نشد، هرگز
فرستاده نمی‌شود. ارسال واقعی کار `OutboxService.dispatch` است.

## انتخاب کانال

```
کانال‌های نهایی = (ترجیح کاربر برای دستهٔ این نوع، یا پیش‌فرض دسته)
                ∩ کانال‌های فعال سامانه
                − پیامک، اگر نوع اجازهٔ پیامک ندارد
                + پیامک و پیام‌رسان‌های پیوندشده، اگر اولویت URGENT است
                + کانال‌های اجباری فراخوان
                − هر کانالی که گیرنده برایش نشانی ندارد
```

ایمیل فقط به نشانی **تأییدشده** می‌رود: ایمیلی که کاربر فقط تایپ کرده
ممکن است مال کس دیگری باشد.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from silp.core.config import Settings, get_settings
from silp.core.exceptions import NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.domain.notifications import catalog, schedule
from silp.domain.notifications.catalog import Channel, Group, Kind, Priority
from silp.domain.notifications.push import subscription_recipient
from silp.domain.notifications.templating import TemplateError, render
from silp.integrations.messaging import enabled_channels
from silp.models.identity import User
from silp.models.messaging import (
    MessageTemplate,
    Notification,
    NotificationPreference,
    OutboxMessage,
    PushSubscription,
    UserChannel,
)
from silp.models.profile import Profile

log = get_logger("silp.notifications")

#: §4.12 — «اعلان‌های خوانده‌شده، ۹۰ روز، سپس آرشیو».
ARCHIVE_AFTER = timedelta(days=90)
#: §4.12 — «outbox_messages ارسال‌شده، ۳۰ روز».
SENT_OUTBOX_RETENTION = timedelta(days=30)
MAX_FEED_PAGE = 50
#: پیام‌هایی که هنوز نرفته‌اند و بازنویسی یا پس‌گرفتنشان معنا دارد.
PENDING_OUTBOX = ("QUEUED", "FAILED")
#: کانال Redis که جریان SSE هر کاربر به آن گوش می‌دهد.
WAKEUP_PREFIX = "silp:notify:"
_PENDING_WAKEUPS = "silp_notify_users"


def _now() -> datetime:
    return datetime.now(UTC)


def wakeup_channel(user_id: uuid.UUID | str) -> str:
    return f"{WAKEUP_PREFIX}{user_id}"


class NotificationService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._templates: dict[tuple[str, str], MessageTemplate | None] = {}

    # ── ساختن ──────────────────────────────────────────────────────────
    async def notify(
        self,
        kind_code: str,
        user_ids: Iterable[uuid.UUID],
        values: Mapping[str, object] | None = None,
        *,
        action_url: str | None = None,
        priority: Priority | None = None,
        dedup_key: str | None = None,
        data: Mapping[str, Any] | None = None,
        force_channels: Sequence[Channel] = (),
    ) -> list[Notification]:
        """اعلان برای یک یا چند گیرنده. خروجی: اعلان‌های **تازه** ساخته‌شده.

        با `dedup_key`، گیرنده‌ای که همین کلید را قبلاً داشته، اعلان تازه و
        پیام صف تازه نمی‌گیرد — کارهای زمان‌بندی‌شده به همین بی‌اثرند (§7.11).
        """
        kind = catalog.kind(kind_code)
        level: Priority = priority or kind.priority
        recipients = list(dict.fromkeys(user_ids))
        if not recipients:
            return []
        if action_url is not None and (
            not action_url.startswith("/") or action_url.startswith("//")
        ):
            msg = f"action_url باید مسیر داخلی باشد: {action_url}"
            raise ValueError(msg)

        in_app = await self.template(kind.code, "IN_APP")
        if in_app is None:
            raise TemplateError(f"الگوی داخلی «{kind.code}» تعریف نشده یا غیرفعال است.")

        users = await self._recipients(recipients)
        if not users:
            return []
        base = {k: _str(v) for k, v in (values or {}).items()}
        link = self.absolute_url(action_url)

        rows: list[dict[str, Any]] = []
        per_user_values: dict[uuid.UUID, dict[str, str]] = {}
        for user_id in recipients:
            info = users.get(user_id)
            if info is None:
                continue
            user_values = {**base, "name": info.first_name, "link": link}
            rendered = render(in_app.subject or kind.title_fa, in_app.body, user_values)
            per_user_values[user_id] = user_values
            rows.append(
                {
                    "user_id": user_id,
                    "kind": kind.code,
                    "kind_group": kind.group,
                    "title": rendered.subject or kind.title_fa,
                    "body": rendered.body,
                    "action_url": action_url,
                    "priority": level,
                    "data": dict(data or {}),
                    "dedup_key": dedup_key,
                }
            )
        if not rows:
            return []

        statement = insert(Notification).values(rows)
        if dedup_key is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=["user_id", "dedup_key"],
                index_where=text("dedup_key IS NOT NULL"),
            )
        created = list(await self.session.scalars(statement.returning(Notification)))
        if not created:
            return []

        channels = await self._channels_for(
            kind, level, [n.user_id for n in created], force_channels=force_channels
        )
        now = _now()
        outbox: list[dict[str, Any]] = []
        for notification in created:
            info = users[notification.user_id]
            for channel in channels.get(notification.user_id, ()):
                # Push یک ردیف صف برای هر دستگاه دارد؛ بقیهٔ کانال‌ها یک نشانی.
                for address in info.addresses(channel):
                    outbox.append(
                        {
                            "channel": channel,
                            "recipient": address,
                            "template": kind.code,
                            "payload": {"values": per_user_values[notification.user_id]},
                            "notification_id": notification.id,
                            "user_id": notification.user_id,
                            "priority": level,
                            "next_attempt_at": self.first_attempt_at(now, level),
                        }
                    )
        if outbox:
            await self.session.execute(insert(OutboxMessage).values(outbox))

        _mark_wakeup(self.session, [n.user_id for n in created])
        log.info(
            "notifications_created",
            kind=kind.code,
            count=len(created),
            outbox=len(outbox),
        )
        return created

    async def enqueue_direct(
        self,
        *,
        template: str,
        channel: Channel,
        recipient: str,
        values: Mapping[str, object],
        user_id: uuid.UUID | None = None,
        priority: Priority = "URGENT",
    ) -> OutboxMessage:
        """پیام صف بدون اعلان — کد تأیید پیام‌رسان (ADR-0013).

        پیش‌فرض `URGENT` است: کاربر همین حالا منتظر کد است و ساعت آرام
        نباید آن را تا صبح نگه دارد.
        """
        catalog.template_variables(template)  # الگوی ناشناخته همین‌جا رد می‌شود
        message = OutboxMessage(
            channel=channel,
            recipient=recipient,
            template=template,
            payload={"values": {k: _str(v) for k, v in values.items()}},
            user_id=user_id,
            priority=priority,
            next_attempt_at=self.first_attempt_at(_now(), priority),
        )
        self.session.add(message)
        await self.session.flush()
        return message

    def first_attempt_at(self, now: datetime, priority: Priority | str) -> datetime:
        """ساعت آرام — FR-MSG-02. فقط `URGENT` از آن عبور می‌کند."""
        if priority == "URGENT":
            return now
        return schedule.release_time(
            now,
            start=self.settings.quiet_hours_start,
            end=self.settings.quiet_hours_end,
        )

    def absolute_url(self, path: str | None) -> str:
        base = self.settings.frontend_url.rstrip("/")
        return f"{base}{path}" if path else base

    async def template(self, code: str, channel: str) -> MessageTemplate | None:
        """الگوی فعال، با کش درون نمونه — یک اعلان گروهی یک بار می‌خواند."""
        key = (code, channel)
        if key not in self._templates:
            row = await self.session.get(MessageTemplate, key)
            self._templates[key] = row if row is not None and row.is_active else None
        return self._templates[key]

    # ── انتخاب کانال ───────────────────────────────────────────────────
    async def _channels_for(
        self,
        kind: Kind,
        level: Priority,
        user_ids: list[uuid.UUID],
        *,
        force_channels: Sequence[Channel],
    ) -> dict[uuid.UUID, tuple[str, ...]]:
        enabled = set(enabled_channels(self.settings))
        prefs = await self._preference_rows(user_ids, group=kind.group)
        result: dict[uuid.UUID, tuple[str, ...]] = {}
        for user_id in user_ids:
            wanted = set(prefs.get(user_id, catalog.DEFAULT_CHANNELS[kind.group]))
            if level == "URGENT" and kind.allow_sms:
                # FR-EDU-06 — «URGENT علاوه بر اعلان داخلی، پیامک/تلگرام هم».
                wanted |= {"SMS", *catalog.LINKABLE_CHANNELS}
            wanted |= set(force_channels)
            if not kind.allow_sms:
                wanted.discard("SMS")
            result[user_id] = tuple(
                c for c in catalog.EXTERNAL_CHANNELS if c in wanted and c in enabled
            )
        return result

    async def _preference_rows(
        self, user_ids: list[uuid.UUID], *, group: Group | None = None
    ) -> dict[uuid.UUID, list[str]]:
        query = select(NotificationPreference).where(NotificationPreference.user_id.in_(user_ids))
        if group is not None:
            query = query.where(NotificationPreference.kind_group == group)
        return {row.user_id: list(row.channels) for row in await self.session.scalars(query)}

    async def _recipients(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, _Recipient]:
        rows = await self.session.execute(
            select(
                User.id,
                User.mobile,
                User.email,
                User.email_verified_at,
                Profile.first_name,
            )
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(
                User.id.in_(user_ids),
                User.deleted_at.is_(None),
                User.status == "ACTIVE",
            )
        )
        recipients = {
            row.id: _Recipient(
                mobile=row.mobile,
                email=row.email if row.email_verified_at is not None else None,
                first_name=row.first_name or "",
            )
            for row in rows
        }
        if recipients:
            for link in await self.session.scalars(
                select(UserChannel).where(
                    UserChannel.user_id.in_(list(recipients)),
                    UserChannel.verified_at.is_not(None),
                )
            ):
                if link.address:
                    recipients[link.user_id].linked[link.channel] = link.address
            for subscription in await self.session.scalars(
                select(PushSubscription)
                .where(PushSubscription.user_id.in_(list(recipients)))
                .order_by(PushSubscription.created_at)
            ):
                recipients[subscription.user_id].push.append(
                    subscription_recipient(
                        subscription.endpoint, subscription.p256dh, subscription.auth
                    )
                )
        return recipients

    # ── بازنویسی و پس‌گرفتن — ADR-0021 ─────────────────────────────────
    async def revise(self, kind_code: str, dedup_key: str, values: Mapping[str, object]) -> int:
        """متن اعلان‌هایی که از یک منبع ویرایش‌شده ساخته شده‌اند را از نو می‌سازد.

        دوباره فرستاده نمی‌شود: فقط متن مرکز اعلان و بار پیام‌هایی که هنوز در
        صف‌اند (`QUEUED`/`FAILED`) عوض می‌شود. پیامی که رفته، رفته است.
        خروجی: شمار اعلان‌های بازنویسی‌شده.
        """
        kind = catalog.kind(kind_code)
        in_app = await self.template(kind.code, "IN_APP")
        if in_app is None:
            return 0
        notifications = list(
            await self.session.scalars(
                select(Notification).where(
                    Notification.kind == kind.code, Notification.dedup_key == dedup_key
                )
            )
        )
        if not notifications:
            return 0
        first_names = dict(
            (
                await self.session.execute(
                    select(Profile.user_id, Profile.first_name).where(
                        Profile.user_id.in_([n.user_id for n in notifications])
                    )
                )
            )
            .tuples()
            .all()
        )
        base = {k: _str(v) for k, v in values.items()}
        for notification in notifications:
            user_values = {
                **base,
                "name": first_names.get(notification.user_id) or "",
                "link": self.absolute_url(notification.action_url),
            }
            rendered = render(in_app.subject or kind.title_fa, in_app.body, user_values)
            notification.title = rendered.subject or kind.title_fa
            notification.body = rendered.body
            await self.session.execute(
                update(OutboxMessage)
                .where(
                    OutboxMessage.notification_id == notification.id,
                    OutboxMessage.status.in_(PENDING_OUTBOX),
                )
                .values(payload={"values": user_values})
            )
        await self.session.flush()
        return len(notifications)

    async def retract(self, dedup_key: str) -> int:
        """اعلان‌های یک منبع حذف‌شده را پس می‌گیرد، با پیام‌هایی که هنوز نرفته‌اند.

        بی این کار دانشجو اعلانی می‌خواند که پیوندش به چیزی ناموجود می‌رود، و
        پیامکِ صف‌مانده پس از حذف هم فرستاده می‌شد (`notification_id` فقط
        `SET NULL` می‌شود). خروجی: شمار اعلان‌های حذف‌شده.
        """
        ids = select(Notification.id).where(Notification.dedup_key == dedup_key)
        await self.session.execute(
            delete(OutboxMessage).where(
                OutboxMessage.notification_id.in_(ids),
                OutboxMessage.status.in_(PENDING_OUTBOX),
            )
        )
        result = await self.session.execute(
            delete(Notification).where(Notification.dedup_key == dedup_key)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ── مرکز اعلان — FR-MSG-01 ─────────────────────────────────────────
    async def feed(
        self,
        user_id: uuid.UUID,
        *,
        before: uuid.UUID | None = None,
        limit: int = 20,
        unread_only: bool = False,
        group: Group | None = None,
    ) -> tuple[list[Notification], uuid.UUID | None]:
        """فهرست کرسری — تازه‌ترین اول. uuidv7 به ترتیب زمان است."""
        size = max(1, min(limit, MAX_FEED_PAGE))
        query = select(Notification).where(
            Notification.user_id == user_id, Notification.archived_at.is_(None)
        )
        if before is not None:
            query = query.where(Notification.id < before)
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        if group is not None:
            query = query.where(Notification.kind_group == group)
        query = query.order_by(Notification.id.desc()).limit(size + 1)
        rows = list(await self.session.scalars(query))
        next_cursor = rows[size - 1].id if len(rows) > size else None
        return rows[:size], next_cursor

    async def since(self, user_id: uuid.UUID, after: uuid.UUID | None) -> list[Notification]:
        """اعلان‌های تازه‌تر از `after` — برای جریان SSE، قدیمی‌ترین اول."""
        query = select(Notification).where(
            Notification.user_id == user_id, Notification.archived_at.is_(None)
        )
        if after is not None:
            query = query.where(Notification.id > after)
        query = query.order_by(Notification.id.desc()).limit(MAX_FEED_PAGE)
        rows = await self.session.scalars(query)
        return list(reversed(list(rows)))

    async def latest_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        latest: uuid.UUID | None = await self.session.scalar(
            # PostgreSQL برای uuid تابع max ندارد؛ uuidv7 به ترتیب زمان است.
            select(Notification.id)
            .where(Notification.user_id == user_id)
            .order_by(Notification.id.desc())
            .limit(1)
        )
        return latest

    async def unread_count(self, user_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
                Notification.archived_at.is_(None),
            )
        )
        return int(count or 0)

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        notification = await self.session.get(Notification, notification_id)
        # §6.4 قاعدهٔ ۴ — اعلان دیگری برای این کاربر وجود ندارد.
        if notification is None or notification.user_id != user_id:
            raise NotFound("این اعلان پیدا نشد.")
        if notification.read_at is None:
            notification.read_at = _now()
            _mark_wakeup(self.session, [user_id])
            await self.session.commit()
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
                Notification.archived_at.is_(None),
            )
            .values(read_at=_now())
        )
        _mark_wakeup(self.session, [user_id])
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    # ── ترجیحات — FR-MSG-02 ────────────────────────────────────────────
    async def preferences(self, user_id: uuid.UUID) -> dict[Group, tuple[str, ...]]:
        rows = {
            row.kind_group: row.channels
            for row in await self.session.scalars(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            )
        }
        return {
            group: tuple(rows.get(group, catalog.DEFAULT_CHANNELS[group]))
            for group in catalog.GROUPS
        }

    async def set_preferences(
        self, user_id: uuid.UUID, choices: Mapping[Group, Sequence[str]]
    ) -> dict[Group, tuple[str, ...]]:
        """ذخیرهٔ ترجیح دسته‌هایی که آمده‌اند؛ بقیه دست نمی‌خورند."""
        enabled = {"IN_APP", *enabled_channels(self.settings)}
        for group_name, channels in choices.items():
            if group_name not in catalog.GROUPS:
                raise ValidationFailed(f"دستهٔ اعلان ناشناخته: {group_name}")
            group: Group = group_name
            try:
                normalized = catalog.normalize_channels(group, list(channels))
            except ValueError as exc:
                raise ValidationFailed(str(exc)) from exc
            unavailable = [c for c in normalized if c not in enabled]
            if unavailable:
                names = "، ".join(catalog.CHANNEL_TITLE_FA[c] for c in unavailable)
                raise ValidationFailed(f"این کانال‌ها در دسترس نیستند: {names}")
            await self._upsert_preference(user_id, group, normalized)
        await self.session.commit()
        return await self.preferences(user_id)

    async def add_channel_everywhere(self, user_id: uuid.UUID, channel: Channel) -> None:
        """پس از پیوند پیام‌رسان: همان کانال به همهٔ دسته‌ها افزوده می‌شود.

        کاربری که تلگرامش را وصل کرده، انتظار دارد اعلان را آنجا ببیند؛
        اگر لازم بود، از تنظیمات برای یک دسته خاموشش می‌کند. بدون commit.
        """
        current = await self.preferences(user_id)
        for group, channels in current.items():
            await self._upsert_preference(
                user_id, group, catalog.normalize_channels(group, [*channels, channel])
            )

    async def _upsert_preference(
        self, user_id: uuid.UUID, group: Group, channels: Sequence[str]
    ) -> None:
        statement = insert(NotificationPreference).values(
            user_id=user_id, kind_group=group, channels=list(channels)
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "kind_group"],
                set_={"channels": statement.excluded.channels},
            )
        )

    # ── نگهداری — §4.12 ────────────────────────────────────────────────
    async def cleanup(self, *, now: datetime | None = None) -> tuple[int, int]:
        """آرشیو خوانده‌شده‌های ۹۰ روزه و حذف پیام‌های ارسال‌شدهٔ ۳۰ روزه."""
        moment = now or _now()
        archived = await self.session.execute(
            update(Notification)
            .where(
                Notification.archived_at.is_(None),
                Notification.read_at.is_not(None),
                Notification.created_at < moment - ARCHIVE_AFTER,
            )
            .values(archived_at=moment)
        )
        purged = await self.session.execute(
            delete(OutboxMessage).where(
                OutboxMessage.status == "SENT",
                OutboxMessage.sent_at < moment - SENT_OUTBOX_RETENTION,
            )
        )
        await self.session.commit()
        return int(getattr(archived, "rowcount", 0) or 0), int(getattr(purged, "rowcount", 0) or 0)


class _Recipient:
    __slots__ = ("email", "first_name", "linked", "mobile", "push")

    def __init__(self, *, mobile: str | None, email: str | None, first_name: str) -> None:
        self.mobile = mobile
        self.email = email
        self.first_name = first_name
        self.linked: dict[str, str] = {}
        self.push: list[str] = []

    def addresses(self, channel: str) -> list[str]:
        """نشانی‌های گیرنده در یک کانال؛ خالی یعنی کانال برایش کار نمی‌کند."""
        if channel == "PUSH":
            return list(self.push)
        if channel == "SMS":
            single = self.mobile
        elif channel == "EMAIL":
            single = self.email
        else:
            single = self.linked.get(channel)
        return [single] if single else []


def _str(value: object) -> str:
    return "" if value is None else str(value)


# ── بیدارباش SSE پس از commit ──────────────────────────────────────────
#
# جریان SSE هر کاربر به کانال Redis خودش گوش می‌دهد. نشانه **پس از**
# commit فرستاده می‌شود: اگر پیش از آن برود، کلاینت دوباره می‌خواند و
# اعلانی را که هنوز تثبیت نشده نمی‌بیند. اگر Redis نباشد، جریان با
# پرسش دوره‌ای کار می‌کند (NFR-11) — فقط کندتر.
_background: set[asyncio.Task[None]] = set()


def _mark_wakeup(session: AsyncSession, user_ids: Iterable[uuid.UUID]) -> None:
    pending: set[uuid.UUID] = session.sync_session.info.setdefault(_PENDING_WAKEUPS, set())
    pending.update(user_ids)


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    users = session.info.pop(_PENDING_WAKEUPS, None)
    if not users:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_publish_wakeups(list(users)))
    _background.add(task)
    task.add_done_callback(_background.discard)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_WAKEUPS, None)


async def flush_wakeups() -> None:
    """منتظر ماندن برای بیدارباش‌های در راه.

    API و کارگر ARQ حلقهٔ رویداد ماندگار دارند و لازمشان نیست. اسکریپت
    کوتاه‌عمری که اعلان می‌سازد و بلافاصله `asyncio.run` را تمام می‌کند،
    بدون این بیدارباش را گم می‌کند — اعلان سالم است، فقط جریان SSE تا
    پرسش بعدی (حداکثر ۲۰ ثانیه) صبر می‌کند.
    """
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


async def _publish_wakeups(user_ids: list[uuid.UUID]) -> None:
    from redis.exceptions import RedisError

    from silp.core.redis import get_redis

    try:
        client = get_redis()
        for user_id in user_ids:
            await client.publish(wakeup_channel(user_id), "1")
    except (RedisError, OSError) as exc:
        log.debug("notification_wakeup_skipped", error=type(exc).__name__)


__all__ = [
    "ARCHIVE_AFTER",
    "MAX_FEED_PAGE",
    "SENT_OUTBOX_RETENTION",
    "NotificationService",
    "flush_wakeups",
    "wakeup_channel",
]
