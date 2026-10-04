"""گفت‌وگوی استاد–دانشجو — ADR-0036 §۲.۴.

قواعد دسترسی (همه اینجا، نه فقط در مسیر):

* **کادر** = دارندهٔ `ANNOUNCEMENT_PUBLISH` در قلمرو همان ارائه (استاد، دستیار، مدیر).
* **دانشجو** = ثبت‌نام فعال در ارائه.
* کانال درس (`OFFERING`): فقط کادر می‌نویسد؛ دانشجوی ثبت‌نام‌شده می‌خواند.
* گفت‌وگوی مستقیم (`DIRECT`): فقط کادرِ همان ارائه و همان یک دانشجو؛ هر دو می‌نویسند.
* دانشجو هرگز با دانشجوی دیگر یا با کادرِ ارائه‌ای که در آن نیست گفت‌وگو نمی‌کند.

متن گفت‌وگو در همین سامانه می‌ماند؛ به پیام‌رسان بیرونی فقط اعلان کوتاه می‌رود.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, PermissionDenied
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.models.conversation import Conversation, ConversationMember, Message
from silp.models.education import Course, CourseOffering, Enrollment
from silp.models.identity import User
from silp.models.profile import Profile
from silp.models.roster import RosterEntry
from silp.services import authz
from silp.services.notification_service import NotificationService

log = get_logger("silp.messaging")

MAX_BODY = 4000
PREVIEW_LEN = 90
Audience = Literal["ALL", "SELECTED"]


@dataclass(frozen=True)
class ConversationSummary:
    id: uuid.UUID
    kind: str
    offering_id: uuid.UUID
    course_title: str
    title: str
    last_message_at: datetime | None
    last_preview: str | None
    unread: int
    can_write: bool


@dataclass(frozen=True)
class MessageView:
    id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    mine: bool
    from_staff: bool
    body: str
    reply_to_id: uuid.UUID | None
    created_at: datetime
    deleted: bool


@dataclass(frozen=True)
class ThreadRow:
    student_id: uuid.UUID | None
    name: str
    has_account: bool
    conversation_id: uuid.UUID | None
    last_preview: str | None
    last_message_at: datetime | None
    unread: int


@dataclass(frozen=True)
class SendResult:
    sent: int
    skipped_no_account: int


def clean_body(body: str) -> str:
    text = body.strip()
    if not text:
        raise Conflict("متن پیام خالی است.", code="MESSAGE_EMPTY")
    if len(text) > MAX_BODY:
        raise Conflict(f"پیام حداکثر {MAX_BODY} نویسه می‌تواند باشد.", code="MESSAGE_TOO_LONG")
    return text


def preview(body: str) -> str:
    flat = " ".join(body.split())
    return flat if len(flat) <= PREVIEW_LEN else flat[: PREVIEW_LEN - 1] + "…"


class MessagingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── نقش‌ها ─────────────────────────────────────────────────────────
    async def is_staff(self, actor: CurrentUser, offering_id: uuid.UUID) -> bool:
        return await authz.has_permission(
            self.session, actor, Permission.ANNOUNCEMENT_PUBLISH, offering_id
        )

    async def _enrolled(self, user_id: uuid.UUID, offering_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Enrollment.id).where(
                Enrollment.offering_id == offering_id,
                Enrollment.student_id == user_id,
                Enrollment.status.in_(("ACTIVE", "COMPLETED")),
            )
        )
        return found is not None

    async def _offering(self, offering_id: uuid.UUID) -> tuple[CourseOffering, str]:
        row = (
            await self.session.execute(
                select(CourseOffering, Course.title_fa)
                .join(Course, Course.id == CourseOffering.course_id)
                .where(CourseOffering.id == offering_id, CourseOffering.deleted_at.is_(None))
            )
        ).first()
        if row is None:
            raise NotFound("ارائهٔ درس پیدا نشد.")
        return row[0], row[1]

    async def _names(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Profile.user_id, Profile.first_name, Profile.last_name).where(
                    Profile.user_id.in_(user_ids)
                )
            )
        ).all()
        names = {r[0]: f"{r[1]} {r[2]}".strip() for r in rows}
        for missing in user_ids - names.keys():
            user = await self.session.get(User, missing)
            names[missing] = (user.username or "کاربر") if user else "کاربر"
        return names

    # ── ساخت گفت‌وگو ───────────────────────────────────────────────────
    async def _channel(self, offering_id: uuid.UUID, creator: uuid.UUID) -> Conversation:
        await self.session.execute(
            pg_insert(Conversation)
            .values(kind="OFFERING", offering_id=offering_id, created_by=creator)
            .on_conflict_do_nothing(
                index_elements=["offering_id"], index_where=Conversation.kind == "OFFERING"
            )
        )
        conv = await self.session.scalar(
            select(Conversation).where(
                Conversation.offering_id == offering_id, Conversation.kind == "OFFERING"
            )
        )
        assert conv is not None
        return conv

    async def channel_for(self, actor: CurrentUser, offering_id: uuid.UUID) -> Conversation:
        await self._offering(offering_id)
        if not await self.is_staff(actor, offering_id):
            raise PermissionDenied()
        return await self._channel(offering_id, actor.id)

    async def _add_member(self, conv_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
        await self.session.execute(
            pg_insert(ConversationMember)
            .values(conversation_id=conv_id, user_id=user_id, role=role)
            .on_conflict_do_nothing()
        )

    async def open_direct(
        self, actor: CurrentUser, offering_id: uuid.UUID, student_id: uuid.UUID
    ) -> Conversation:
        await self._offering(offering_id)
        if not await self.is_staff(actor, offering_id):
            raise PermissionDenied()
        if not await self._enrolled(student_id, offering_id):
            raise NotFound("این کاربر دانشجوی فعال این درس نیست.")
        await self.session.execute(
            pg_insert(Conversation)
            .values(
                kind="DIRECT",
                offering_id=offering_id,
                student_id=student_id,
                created_by=actor.id,
            )
            .on_conflict_do_nothing(
                index_elements=["offering_id", "student_id"],
                index_where=Conversation.kind == "DIRECT",
            )
        )
        conv = await self.session.scalar(
            select(Conversation).where(
                Conversation.offering_id == offering_id,
                Conversation.kind == "DIRECT",
                Conversation.student_id == student_id,
            )
        )
        assert conv is not None
        await self._add_member(conv.id, student_id, "STUDENT")
        await self._add_member(conv.id, actor.id, "STAFF")
        return conv

    # ── دسترسی به یک گفت‌وگو ───────────────────────────────────────────
    async def _access(
        self, actor: CurrentUser, conversation_id: uuid.UUID
    ) -> tuple[Conversation, str, bool]:
        """خروجی: (گفت‌وگو، نقش `STAFF|STUDENT`، اجازهٔ نوشتن)."""
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None:
            raise NotFound("گفت‌وگو پیدا نشد.")
        staff = await self.is_staff(actor, conv.offering_id)
        if conv.kind == "OFFERING":
            if staff:
                return conv, "STAFF", True
            if await self._enrolled(actor.id, conv.offering_id):
                return conv, "STUDENT", False
        elif conv.kind == "DIRECT":
            if staff:
                return conv, "STAFF", True
            if conv.student_id == actor.id and await self._enrolled(actor.id, conv.offering_id):
                return conv, "STUDENT", True
        # وجود گفت‌وگو را به غیرعضو لو نمی‌دهیم.
        raise NotFound("گفت‌وگو پیدا نشد.")

    # ── نوشتن ──────────────────────────────────────────────────────────
    async def send(
        self,
        actor: CurrentUser,
        conversation_id: uuid.UUID,
        body: str,
        *,
        reply_to_id: uuid.UUID | None = None,
    ) -> Message:
        conv, role, can_write = await self._access(actor, conversation_id)
        if not can_write:
            raise PermissionDenied(
                "در کانال درس فقط استاد و دستیار می‌نویسند؛ پیامت را در گفت‌وگوی خصوصی بفرست."
            )
        text = clean_body(body)
        if reply_to_id is not None:
            parent = await self.session.get(Message, reply_to_id)
            if parent is None or parent.conversation_id != conv.id:
                raise Conflict("پیام مرجع در این گفت‌وگو نیست.", code="REPLY_INVALID")
        message = await self._post(conv, actor.id, role, text, reply_to_id)
        await self._notify(conv, actor.id, text)
        return message

    async def _post(
        self,
        conv: Conversation,
        sender_id: uuid.UUID,
        role: str,
        text: str,
        reply_to_id: uuid.UUID | None,
    ) -> Message:
        message = Message(
            conversation_id=conv.id, sender_id=sender_id, body=text, reply_to_id=reply_to_id
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        conv.last_message_at = message.created_at
        # فرستنده تا پیام خودش را خوانده است.
        await self._add_member(conv.id, sender_id, role)
        await self.session.execute(
            update(ConversationMember)
            .where(
                ConversationMember.conversation_id == conv.id,
                ConversationMember.user_id == sender_id,
            )
            .values(last_read_at=message.created_at)
        )
        return message

    async def _notify(self, conv: Conversation, sender_id: uuid.UUID, text: str) -> None:
        _, course_title = await self._offering(conv.offering_id)
        if conv.kind == "OFFERING":
            recipients = list(
                await self.session.scalars(
                    select(Enrollment.student_id).where(
                        Enrollment.offering_id == conv.offering_id,
                        Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                    )
                )
            )
        else:
            recipients = list(
                await self.session.scalars(
                    select(ConversationMember.user_id).where(
                        ConversationMember.conversation_id == conv.id
                    )
                )
            )
        recipients = [u for u in recipients if u != sender_id]
        if not recipients:
            return
        sender = (await self._names({sender_id}))[sender_id]
        await NotificationService(self.session).notify(
            "MESSAGE_RECEIVED",
            recipients,
            {"sender": sender, "course": course_title, "preview": preview(text)},
            action_url=f"/messages/{conv.id}",
        )

    async def send_to_audience(
        self,
        actor: CurrentUser,
        offering_id: uuid.UUID,
        *,
        audience: Audience,
        student_ids: list[uuid.UUID],
        body: str,
    ) -> SendResult:
        """«به همه» ⇒ یک پست در کانال درس؛ «به منتخب» ⇒ یک پیام خصوصی برای هر نفر."""
        text = clean_body(body)
        await self._offering(offering_id)
        if not await self.is_staff(actor, offering_id):
            raise PermissionDenied()
        if audience == "ALL":
            conv = await self._channel(offering_id, actor.id)
            await self._post(conv, actor.id, "STAFF", text, None)
            await self._notify(conv, actor.id, text)
            count = await self.session.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(
                    Enrollment.offering_id == offering_id,
                    Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                )
            )
            return SendResult(
                sent=int(count or 0), skipped_no_account=await self._unclaimed(offering_id)
            )
        if not student_ids:
            raise Conflict("هیچ دانشجویی انتخاب نشده است.", code="NO_RECIPIENTS")
        sent = 0
        skipped = 0
        for student_id in dict.fromkeys(student_ids):
            if not await self._enrolled(student_id, offering_id):
                skipped += 1
                continue
            conv = await self.open_direct(actor, offering_id, student_id)
            await self._post(conv, actor.id, "STAFF", text, None)
            await self._notify(conv, actor.id, text)
            sent += 1
        return SendResult(sent=sent, skipped_no_account=skipped)

    async def _unclaimed(self, offering_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(RosterEntry)
            .where(RosterEntry.offering_id == offering_id, RosterEntry.user_id.is_(None))
        )
        return int(count or 0)

    # ── خواندن ─────────────────────────────────────────────────────────
    async def messages(
        self,
        actor: CurrentUser,
        conversation_id: uuid.UUID,
        *,
        before: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[MessageView]:
        conv, _, _ = await self._access(actor, conversation_id)
        query = select(Message).where(Message.conversation_id == conv.id)
        if before is not None:
            query = query.where(Message.id < before)
        rows = list(
            reversed(
                list(await self.session.scalars(query.order_by(Message.id.desc()).limit(limit)))
            )
        )
        names = await self._names({m.sender_id for m in rows})
        student_id = conv.student_id
        out: list[MessageView] = []
        for m in rows:
            out.append(
                MessageView(
                    id=m.id,
                    sender_id=m.sender_id,
                    sender_name=names[m.sender_id],
                    mine=m.sender_id == actor.id,
                    from_staff=(m.sender_id != student_id) if student_id else True,
                    body="" if m.deleted_at else m.body,
                    reply_to_id=m.reply_to_id,
                    created_at=m.created_at,
                    deleted=m.deleted_at is not None,
                )
            )
        return out

    async def mark_read(self, actor: CurrentUser, conversation_id: uuid.UUID) -> None:
        conv, role, _ = await self._access(actor, conversation_id)
        await self._add_member(conv.id, actor.id, role)
        await self.session.execute(
            update(ConversationMember)
            .where(
                ConversationMember.conversation_id == conv.id,
                ConversationMember.user_id == actor.id,
            )
            .values(last_read_at=datetime.now(UTC))
        )

    async def delete_message(self, actor: CurrentUser, message_id: uuid.UUID) -> None:
        """حذف نرم؛ فقط فرستنده یا کادر."""
        message = await self.session.get(Message, message_id)
        if message is None:
            raise NotFound("پیام پیدا نشد.")
        conv, role, _ = await self._access(actor, message.conversation_id)
        if message.sender_id != actor.id and role != "STAFF":
            raise PermissionDenied()
        message.deleted_at = datetime.now(UTC)

    async def inbox(self, actor: CurrentUser) -> list[ConversationSummary]:
        """گفت‌وگوهای کاربر: مستقیم‌های خودش + کانال درس‌هایی که در آن‌هاست."""
        direct_ids = list(
            await self.session.scalars(
                select(ConversationMember.conversation_id).where(
                    ConversationMember.user_id == actor.id
                )
            )
        )
        enrolled = list(
            await self.session.scalars(
                select(Enrollment.offering_id).where(
                    Enrollment.student_id == actor.id,
                    Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                )
            )
        )
        taught = list(
            await self.session.scalars(
                select(CourseOffering.id).where(CourseOffering.instructor_id == actor.id)
            )
        )
        convs = list(
            await self.session.scalars(
                select(Conversation).where(
                    or_(
                        Conversation.id.in_(direct_ids),
                        (Conversation.kind == "OFFERING")
                        & Conversation.offering_id.in_([*enrolled, *taught]),
                    )
                )
            )
        )
        summaries: list[ConversationSummary] = []
        for conv in convs:
            try:
                _, role, can_write = await self._access(actor, conv.id)
            except NotFound:
                continue
            summaries.append(await self._summary(actor, conv, role, can_write))
        summaries.sort(
            key=lambda s: s.last_message_at or datetime.min.replace(tzinfo=UTC), reverse=True
        )
        return summaries

    async def _summary(
        self, actor: CurrentUser, conv: Conversation, role: str, can_write: bool
    ) -> ConversationSummary:
        _, course_title = await self._offering(conv.offering_id)
        last = await self.session.scalar(
            select(Message)
            .where(Message.conversation_id == conv.id, Message.deleted_at.is_(None))
            .order_by(Message.id.desc())
            .limit(1)
        )
        unread = await self._unread(actor.id, conv, role)
        if conv.kind == "OFFERING":
            title = f"کانال درس — {course_title}"
        elif role == "STUDENT":
            title = f"گفت‌وگوی خصوصی با استاد — {course_title}"
        else:
            assert conv.student_id is not None
            title = (await self._names({conv.student_id}))[conv.student_id]
        return ConversationSummary(
            id=conv.id,
            kind=conv.kind,
            offering_id=conv.offering_id,
            course_title=course_title,
            title=title,
            last_message_at=conv.last_message_at,
            last_preview=preview(last.body) if last else None,
            unread=unread,
            can_write=can_write,
        )

    async def _unread(self, user_id: uuid.UUID, conv: Conversation, role: str) -> int:
        member = await self.session.get(ConversationMember, (conv.id, user_id))
        since = member.last_read_at if member else None
        if since is None and role == "STUDENT" and conv.kind == "OFFERING":
            since = await self.session.scalar(
                select(Enrollment.enrolled_at).where(
                    Enrollment.offering_id == conv.offering_id, Enrollment.student_id == user_id
                )
            )
        query = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.sender_id != user_id,
                Message.deleted_at.is_(None),
            )
        )
        if since is not None:
            query = query.where(Message.created_at > since)
        return int(await self.session.scalar(query) or 0)

    async def unread_total(self, actor: CurrentUser) -> int:
        return sum(s.unread for s in await self.inbox(actor))

    # ── نمای استاد: همهٔ دانشجویان ارائه ────────────────────────────────
    async def threads(self, actor: CurrentUser, offering_id: uuid.UUID) -> list[ThreadRow]:
        await self._offering(offering_id)
        if not await self.is_staff(actor, offering_id):
            raise PermissionDenied()
        students = list(
            await self.session.scalars(
                select(Enrollment.student_id).where(
                    Enrollment.offering_id == offering_id,
                    Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                )
            )
        )
        names = await self._names(set(students))
        convs = {
            c.student_id: c
            for c in await self.session.scalars(
                select(Conversation).where(
                    Conversation.offering_id == offering_id, Conversation.kind == "DIRECT"
                )
            )
        }
        rows: list[ThreadRow] = []
        for student_id in students:
            conv = convs.get(student_id)
            last_preview: str | None = None
            unread = 0
            if conv is not None:
                last = await self.session.scalar(
                    select(Message)
                    .where(Message.conversation_id == conv.id, Message.deleted_at.is_(None))
                    .order_by(Message.id.desc())
                    .limit(1)
                )
                last_preview = preview(last.body) if last else None
                unread = await self._unread(actor.id, conv, "STAFF")
            rows.append(
                ThreadRow(
                    student_id=student_id,
                    name=names[student_id],
                    has_account=True,
                    conversation_id=conv.id if conv else None,
                    last_preview=last_preview,
                    last_message_at=conv.last_message_at if conv else None,
                    unread=unread,
                )
            )
        claimed = set(students)
        for entry in await self.session.scalars(
            select(RosterEntry).where(
                RosterEntry.offering_id == offering_id,
                or_(RosterEntry.user_id.is_(None), RosterEntry.user_id.not_in(claimed)),
            )
        ):
            rows.append(
                ThreadRow(
                    student_id=None,
                    name=f"{entry.first_name} {entry.last_name}".strip(),
                    has_account=False,
                    conversation_id=None,
                    last_preview=None,
                    last_message_at=None,
                    unread=0,
                )
            )
        rows.sort(key=lambda r: (not r.has_account, r.name))
        return rows
