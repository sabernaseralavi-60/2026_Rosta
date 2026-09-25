"""پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.

## دسترسی

همان سه‌گانهٔ منابع درس (`courses._require_resource_access`): استادِ ارائه، یا
`OFFERING_MANAGE` در قلمرو ارائه، یا ثبت‌نام `ACTIVE`/`COMPLETED`. دستیار
(`COURSE_WEEK_VIEW_DRAFT`) هم می‌خواند و پاسخ می‌دهد ولی **تأیید نمی‌کند**:
تأیید همان «نظر استاد» است (D-28). بیرونی ۴۰۴ می‌گیرد، نه ۴۰۳ — درسی که در آن
نیست، برایش وجود ندارد.

## امتیاز

اینجا هیچ امتیازی داده نمی‌شود. سرویس فقط رویداد می‌سازد
(`QaReplyPosted/Voted/Endorsed/Removed`) و شنوندهٔ `point_listeners` از روی
**وضعیت ردیف** حساب می‌کند که پاسخ الان چه قاعده‌هایی را باید داشته باشد.

## ناشناس

فقط برای پرسش است (پاسخ ناشناس نداریم؛ امتیاز به پاسخ می‌رسد). نویسندهٔ پرسشِ
ناشناس برای همکلاسی‌ها `None` است؛ خودش و استادِ ارائه می‌بینند.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    DuplicateVote,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import qa as rules
from silp.models.education import CourseOffering, CourseWeek, Enrollment
from silp.models.qa import QaReply, QaReplyVote, QaThread
from silp.services import authz, events

log = get_logger("silp.qa")

ENROLLED_STATUSES = ("ACTIVE", "COMPLETED")


@dataclass(frozen=True, slots=True)
class QaAccess:
    """نقش کاربر در پرسش‌وپاسخ یک ارائه."""

    offering_id: uuid.UUID
    #: استادِ ارائه یا `OFFERING_MANAGE` — پاسخش «رسمی» است، تأیید می‌کند، ناشناس را می‌بیند.
    is_manager: bool
    #: مدیر یا دستیار — هفتهٔ منتشرنشده را هم می‌بیند.
    is_staff: bool
    is_student: bool


@dataclass(frozen=True, slots=True)
class ThreadRow:
    thread: QaThread
    week_number: int | None
    reply_count: int
    #: پاسخ استاد یا پاسخِ تأییدشدهٔ استاد دارد.
    has_official_answer: bool


def _now() -> datetime:
    return datetime.now(UTC)


class QaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── دسترسی ─────────────────────────────────────────────────────────
    async def offering_access(self, offering_id: uuid.UUID, actor: CurrentUser) -> QaAccess:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")
        manager = offering.instructor_id == actor.id or await authz.has_permission(
            self.session, actor, Permission.OFFERING_MANAGE, offering_id
        )
        staff = manager or await authz.has_permission(
            self.session, actor, Permission.COURSE_WEEK_VIEW_DRAFT, offering_id
        )
        student = (
            await self.session.scalar(
                select(Enrollment.id).where(
                    Enrollment.offering_id == offering_id,
                    Enrollment.student_id == actor.id,
                    Enrollment.status.in_(ENROLLED_STATUSES),
                )
            )
            is not None
        )
        if not (staff or student):
            raise NotFound("این ارائه پیدا نشد.")
        return QaAccess(offering_id, is_manager=manager, is_staff=staff, is_student=student)

    async def thread_access(
        self, thread_id: uuid.UUID, actor: CurrentUser
    ) -> tuple[QaThread, QaAccess, int | None]:
        thread = await self.session.get(QaThread, thread_id)
        if thread is None or thread.deleted_at is not None:
            raise NotFound("این پرسش پیدا نشد.")
        access = await self.offering_access(thread.offering_id, actor)
        week_number: int | None = None
        if thread.week_id is not None:
            week = await self.session.get(CourseWeek, thread.week_id)
            if week is not None:
                week_number = week.week_number
                if week.status != "PUBLISHED" and not access.is_staff:
                    raise NotFound("این پرسش پیدا نشد.")
        return thread, access, week_number

    async def reply_access(
        self, reply_id: uuid.UUID, actor: CurrentUser
    ) -> tuple[QaReply, QaThread, QaAccess]:
        reply = await self.session.get(QaReply, reply_id)
        if reply is None or reply.deleted_at is not None:
            raise NotFound("این پاسخ پیدا نشد.")
        thread, access, _ = await self.thread_access(reply.thread_id, actor)
        return reply, thread, access

    def author_visible(self, thread: QaThread, access: QaAccess, viewer: CurrentUser) -> bool:
        """نام پرسندهٔ ناشناس فقط برای خودش و استادِ ارائه."""
        return not thread.is_anonymous or thread.author_id == viewer.id or access.is_manager

    # ── خواندن ─────────────────────────────────────────────────────────
    async def list_threads(
        self,
        access: QaAccess,
        actor: CurrentUser,
        *,
        week_number: int | None,
        filter_: str,
        offset: int,
        limit: int,
    ) -> tuple[list[ThreadRow], int]:
        """بی‌پاسخ اول، سپس تازه‌ترین (بند ۲۰)."""
        live = (
            select(
                QaReply.thread_id.label("thread_id"),
                func.count().label("n"),
                func.bool_or(QaReply.is_official | QaReply.endorsed_at.is_not(None)).label(
                    "settled"
                ),
            )
            .where(QaReply.deleted_at.is_(None))
            .group_by(QaReply.thread_id)
            .subquery()
        )
        reply_count = func.coalesce(live.c.n, 0)
        stmt = (
            select(
                QaThread,
                CourseWeek.week_number.label("week_number"),
                reply_count.label("reply_count"),
                func.coalesce(live.c.settled, literal(False)).label("settled"),
            )
            .outerjoin(CourseWeek, CourseWeek.id == QaThread.week_id)
            .outerjoin(live, live.c.thread_id == QaThread.id)
            .where(QaThread.offering_id == access.offering_id, QaThread.deleted_at.is_(None))
        )
        if not access.is_staff:
            stmt = stmt.where(or_(QaThread.week_id.is_(None), CourseWeek.status == "PUBLISHED"))
        if week_number is not None:
            stmt = stmt.where(CourseWeek.week_number == week_number)
        match filter_:
            case "unanswered":
                stmt = stmt.where(reply_count == 0)
            case "unresolved":
                stmt = stmt.where(QaThread.is_resolved.is_(False))
            case "mine":
                stmt = stmt.where(QaThread.author_id == actor.id)

        total = (
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        rows = await self.session.execute(
            stmt.order_by(
                case((reply_count > 0, 1), else_=0), QaThread.created_at.desc(), QaThread.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        return [
            ThreadRow(thread, week_number_, int(n), bool(settled))
            for thread, week_number_, n, settled in rows.tuples().all()
        ], int(total)

    async def replies(self, thread_id: uuid.UUID) -> list[QaReply]:
        """پاسخ‌های زنده — رسمی و تأییدشده و پررأی بالاتر (پاسخ بهتر بالاست)."""
        rows = await self.session.scalars(
            select(QaReply)
            .where(QaReply.thread_id == thread_id, QaReply.deleted_at.is_(None))
            .order_by(
                QaReply.is_official.desc(),
                QaReply.endorsed_at.is_not(None).desc(),
                QaReply.helpful_count.desc(),
                QaReply.created_at,
                QaReply.id,
            )
        )
        return list(rows)

    async def voted_by(self, user_id: uuid.UUID, reply_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not reply_ids:
            return set()
        rows = await self.session.scalars(
            select(QaReplyVote.reply_id).where(
                QaReplyVote.user_id == user_id, QaReplyVote.reply_id.in_(reply_ids)
            )
        )
        return set(rows)

    # ── پرسش ───────────────────────────────────────────────────────────
    async def create_thread(
        self,
        access: QaAccess,
        actor: CurrentUser,
        *,
        title: str,
        body: str,
        week_number: int | None,
        is_anonymous: bool,
    ) -> QaThread:
        clean_title = rules.clean_title(title)
        clean_body = body.strip()
        if problem := rules.validate_thread(clean_title, clean_body):
            raise ValidationFailed(problem)
        week_id: uuid.UUID | None = None
        if week_number is not None:
            week = await self.session.scalar(
                select(CourseWeek).where(
                    CourseWeek.offering_id == access.offering_id,
                    CourseWeek.week_number == week_number,
                )
            )
            if week is None or (week.status != "PUBLISHED" and not access.is_staff):
                raise NotFound("این هفته در این درس نیست.")
            week_id = week.id
        thread = QaThread(
            offering_id=access.offering_id,
            week_id=week_id,
            author_id=actor.id,
            is_anonymous=is_anonymous,
            title=clean_title,
            body=clean_body,
        )
        self.session.add(thread)
        await self.session.commit()
        await self.session.refresh(thread)
        log.info("qa_thread_created", thread_id=str(thread.id))
        return thread

    async def set_resolved(
        self, thread: QaThread, access: QaAccess, actor: CurrentUser, *, resolved: bool
    ) -> QaThread:
        """نویسندهٔ پرسش یا استاد — به امتیاز ربطی ندارد (بند ۱۹)."""
        if thread.author_id != actor.id and not access.is_manager:
            raise PermissionDenied("فقط پرسنده یا استاد پرسش را حل‌شده می‌کند.")
        thread.is_resolved = resolved
        await self.session.commit()
        await self.session.refresh(thread)
        return thread

    async def delete_thread(self, thread: QaThread, access: QaAccess, actor: CurrentUser) -> None:
        """پرسنده تا وقتی کسی پاسخ نداده؛ استاد همیشه.

        پرسنده‌ای که پرسش پاسخ‌گرفته‌اش را پاک کند، امتیاز پاسخ‌دهندگان را
        برمی‌گرداند — سوءاستفاده‌ای که با «حل‌شده» جواب داده می‌شود.
        """
        if thread.author_id != actor.id and not access.is_manager:
            raise PermissionDenied("فقط پرسنده یا استاد پرسش را حذف می‌کند.")
        live = list(
            await self.session.scalars(
                select(QaReply).where(QaReply.thread_id == thread.id, QaReply.deleted_at.is_(None))
            )
        )
        if not access.is_manager and any(r.author_id != actor.id for r in live):
            raise Conflict("پرسشی که پاسخ گرفته حذف نمی‌شود؛ می‌توانی آن را «حل‌شده» کنی.")
        thread.deleted_at = _now()
        await self.session.flush()
        for reply in live:
            await events.publish(self.session, events.QaReplyRemoved(reply_id=reply.id))
        await self.session.commit()

    # ── پاسخ ───────────────────────────────────────────────────────────
    async def post_reply(
        self, thread: QaThread, access: QaAccess, actor: CurrentUser, *, body: str
    ) -> QaReply:
        clean_body = body.strip()
        if problem := rules.validate_reply(clean_body):
            raise ValidationFailed(problem)
        reply = QaReply(
            thread_id=thread.id,
            author_id=actor.id,
            body=clean_body,
            # سرور می‌گذارد، نه بدنه: دستیار «رسمی» نیست (بند ۱۲).
            is_official=access.is_manager,
        )
        self.session.add(reply)
        await self.session.flush()
        await events.publish(self.session, events.QaReplyPosted(reply_id=reply.id))
        await self.session.commit()
        await self.session.refresh(reply)
        log.info("qa_reply_posted", reply_id=str(reply.id))
        return reply

    async def delete_reply(self, reply: QaReply, access: QaAccess, actor: CurrentUser) -> None:
        if reply.author_id != actor.id and not access.is_manager:
            raise PermissionDenied("فقط نویسندهٔ پاسخ یا استاد آن را حذف می‌کند.")
        reply.deleted_at = _now()
        await self.session.flush()
        await events.publish(self.session, events.QaReplyRemoved(reply_id=reply.id))
        await self.session.commit()

    # ── رأی «مفید» — بند ۱۴ ────────────────────────────────────────────
    async def vote(self, reply: QaReply, actor: CurrentUser) -> QaReply:
        if reply.author_id == actor.id:
            raise Conflict("به پاسخ خودت رأی نمی‌دهی.")
        inserted = await self.session.scalar(
            insert(QaReplyVote)
            .values(reply_id=reply.id, user_id=actor.id)
            .on_conflict_do_nothing()
            .returning(literal(1))
        )
        if inserted is None:
            raise DuplicateVote("قبلاً به این پاسخ رأی داده‌ای.")
        await self.session.flush()
        await self.session.refresh(reply)
        await events.publish(self.session, events.QaReplyVoted(reply_id=reply.id))
        await self.session.commit()
        return reply

    async def unvote(self, reply: QaReply, actor: CurrentUser) -> QaReply:
        """پس‌گرفتن رأی — امتیازی که پیش‌تر رسیده برنمی‌گردد (بند ۱۷)."""
        vote = await self.session.get(QaReplyVote, (reply.id, actor.id))
        if vote is None:
            raise NotFound("رأیی برای پس گرفتن نیست.")
        await self.session.delete(vote)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(reply)
        return reply

    # ── تأیید استاد — بند ۱۱، ۱۶ ───────────────────────────────────────
    async def endorse(self, reply: QaReply, access: QaAccess, actor: CurrentUser) -> QaReply:
        self._require_manager(access)
        if reply.is_official:
            raise Conflict("پاسخ استاد نیاز به تأیید ندارد.")
        if reply.author_id == actor.id:
            raise Conflict("پاسخ خودت را تأیید نمی‌کنی.")
        if reply.endorsed_at is not None:
            raise Conflict("این پاسخ قبلاً تأیید شده است.")
        reply.endorsed_by = actor.id
        reply.endorsed_at = _now()
        await self.session.flush()
        await events.publish(self.session, events.QaReplyEndorsed(reply_id=reply.id))
        await self.session.commit()
        await self.session.refresh(reply)
        return reply

    async def unendorse(self, reply: QaReply, access: QaAccess) -> QaReply:
        """برداشتن تأیید — امتیازش با `reconcile` برمی‌گردد (بند ۱۷)."""
        self._require_manager(access)
        if reply.endorsed_at is None:
            raise NotFound("تأییدی برای برداشتن نیست.")
        reply.endorsed_by = None
        reply.endorsed_at = None
        await self.session.flush()
        await events.publish(self.session, events.QaReplyEndorsed(reply_id=reply.id))
        await self.session.commit()
        await self.session.refresh(reply)
        return reply

    @staticmethod
    def _require_manager(access: QaAccess) -> None:
        if not access.is_manager:
            raise PermissionDenied(
                "فقط استاد ارائه پاسخ را تأیید می‌کند.", permission=Permission.OFFERING_MANAGE.value
            )


__all__ = ["ENROLLED_STATUSES", "QaAccess", "QaService", "ThreadRow"]
