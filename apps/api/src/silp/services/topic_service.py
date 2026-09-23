"""بانک موضوع پژوهشی — FR-RES-03، M7-06، ADR-0015.

## وضعیت‌ها

```
پیشنهاد دانشجو ─► PROPOSED ──تأیید──► OPEN ──رزرو──► RESERVED ──تأیید سطح ۱──► TAKEN
ثبت کادر ──────────────────────────► OPEN ◄──آزاد (دستی یا ۳۰ روز بی‌تحرکی)──┘
                     └──رد──► CLOSED ◄──بستن (کادر، از هر وضعیت)
```

* **رزرو اتمی است:** `UPDATE … WHERE status = 'OPEN'` — دو دانشجوی هم‌زمان
  یکی برنده می‌شود و دیگری `TOPIC_ALREADY_RESERVED` می‌گیرد، بدون قفل صریح.
* **یک رزرو باز برای هر نفر** با ایندکس یکتای جزئی — نگه داشتن چند موضوع
  بی‌کار یعنی گرفتن آن‌ها از دیگران، همان «موازی‌کاری» که FR-RES-03
  می‌خواهد جلویش را بگیرد.
* **تحرک** یعنی کار واقعی: رزرو، تحویل سطحی از مسیر پژوهش، و بازخورد
  بازبین. کلیک «هنوز کار می‌کنم» نیست — آن‌وقت قاعدهٔ ۳۰ روز بی‌دندان بود.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, Select, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    NotFound,
    PermissionDenied,
    ReservationLimit,
    TopicAlreadyReserved,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import research as rules
from silp.models.research import (
    NOTE_MAX,
    PREREQUISITES_MAX,
    TOPIC_DESCRIPTION_MAX,
    TOPIC_TITLE_MAX,
    ResearchTopic,
)
from silp.services import authz, events
from silp.services.notification_service import NotificationService

log = get_logger("silp.research.topics")

REVIEW_DECISIONS = ("APPROVE", "REJECT")


@dataclass(slots=True)
class TopicDraft:
    title: str
    description: str
    prerequisites: str | None = None
    level: int | None = None


@dataclass(frozen=True, slots=True)
class StaleStats:
    warned: int = 0
    released: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


class TopicService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── دسترسی ─────────────────────────────────────────────────────────
    async def can_manage(self, actor: CurrentUser | None) -> bool:
        if actor is None:
            return False
        return await authz.has_permission(self.session, actor, Permission.RESEARCH_TOPIC_MANAGE)

    async def _require_manager(self, actor: CurrentUser) -> None:
        if not await self.can_manage(actor):
            raise PermissionDenied(
                "مدیریت بانک موضوع با استاد یا مدیر آموزشی است.",
                permission=Permission.RESEARCH_TOPIC_MANAGE.value,
            )

    @staticmethod
    def visible_to(topic: ResearchTopic, actor: CurrentUser | None, *, manager: bool) -> bool:
        if topic.status in rules.PUBLIC_TOPIC_STATUSES or manager:
            return True
        return actor is not None and actor.id == topic.proposer_id

    # ── خواندن ─────────────────────────────────────────────────────────
    async def get(self, topic_id: uuid.UUID) -> ResearchTopic | None:
        return await self.session.get(ResearchTopic, topic_id)

    async def require(self, topic_id: uuid.UUID, actor: CurrentUser | None) -> ResearchTopic:
        topic = await self.get(topic_id)
        if topic is None or not self.visible_to(topic, actor, manager=await self.can_manage(actor)):
            raise NotFound("موضوع پیدا نشد.")
        return topic

    def list_query(
        self,
        *,
        actor: CurrentUser | None,
        manager: bool,
        status: str | None,
        level: int | None,
        q: str | None,
        mine: bool,
    ) -> Select[tuple[ResearchTopic]]:
        stmt = select(ResearchTopic)
        if mine and actor is not None:
            # «موضوع‌های من» — پیشنهادهایم و رزروهایم، با هر وضعیتی.
            stmt = stmt.where(
                or_(ResearchTopic.proposer_id == actor.id, ResearchTopic.reserved_by == actor.id)
            )
        elif not manager:
            visible: ColumnElement[bool] = ResearchTopic.status.in_(rules.PUBLIC_TOPIC_STATUSES)
            if actor is not None:
                visible = or_(visible, ResearchTopic.proposer_id == actor.id)
            stmt = stmt.where(visible)
        if status is not None:
            stmt = stmt.where(ResearchTopic.status == status)
        if level is not None:
            stmt = stmt.where(or_(ResearchTopic.level == level, ResearchTopic.level.is_(None)))
        if q and q.strip():
            normalized = func.fa_normalize(q.strip())
            stmt = stmt.where(ResearchTopic.search_norm.like(func.concat("%", normalized, "%")))
        # موضوع باز اول — آن چیزی است که دانشجو دنبالش می‌گردد.
        open_first = case(
            {"OPEN": 0, "PROPOSED": 1, "RESERVED": 2, "TAKEN": 3},
            value=ResearchTopic.status,
            else_=4,
        )
        return stmt.order_by(open_first, ResearchTopic.created_at.desc(), ResearchTopic.id)

    async def page(
        self, stmt: Select[tuple[ResearchTopic]], *, offset: int, limit: int
    ) -> tuple[list[ResearchTopic], int]:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(stmt.offset(offset).limit(limit))
        return list(rows), int(total or 0)

    async def current_for(self, user_id: uuid.UUID) -> ResearchTopic | None:
        """موضوع جاری پژوهش این کاربر: رزرو باز، وگرنه آخرین موضوع در حال انجام."""
        result: ResearchTopic | None = await self.session.scalar(
            select(ResearchTopic)
            .where(
                ResearchTopic.reserved_by == user_id,
                ResearchTopic.status.in_(("RESERVED", "TAKEN")),
            )
            .order_by((ResearchTopic.status == "RESERVED").desc(), ResearchTopic.reserved_at.desc())
            .limit(1)
        )
        return result

    # ── ثبت و ویرایش ───────────────────────────────────────────────────
    async def create(self, *, actor: CurrentUser, draft: TopicDraft) -> ResearchTopic:
        """کادر موضوع باز ثبت می‌کند؛ دانشجو پیشنهاد می‌دهد و تا تأیید پنهان است."""
        manager = await self.can_manage(actor)
        if not manager and not await authz.has_permission(
            self.session, actor, Permission.RESEARCH_PARTICIPATE
        ):
            raise PermissionDenied(permission=Permission.RESEARCH_PARTICIPATE.value)
        topic = ResearchTopic(proposer_id=actor.id, status="OPEN" if manager else "PROPOSED")
        self._apply(topic, draft)
        if manager:
            topic.reviewed_by = actor.id
            topic.reviewed_at = _now()
        self.session.add(topic)
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    async def update(
        self, *, topic: ResearchTopic, actor: CurrentUser, draft: TopicDraft
    ) -> ResearchTopic:
        manager = await self.can_manage(actor)
        own_proposal = topic.proposer_id == actor.id and topic.status == "PROPOSED"
        if not manager and not own_proposal:
            raise PermissionDenied("این موضوع را نمی‌توانی ویرایش کنی.")
        self._apply(topic, draft)
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    async def review(
        self, *, topic: ResearchTopic, actor: CurrentUser, decision: str, note: str | None
    ) -> ResearchTopic:
        """پیشنهاد دانشجو — پذیرش امتیاز `TOPIC_PROPOSED` دارد (§9.2)."""
        await self._require_manager(actor)
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        if topic.status != "PROPOSED":
            raise Conflict("فقط پیشنهادهای در انتظار بررسی می‌شوند.")
        cleaned = self._note(note)
        if decision == "REJECT" and cleaned is None:
            raise ValidationFailed("برای رد پیشنهاد، دلیل بنویس.")
        topic.status = "OPEN" if decision == "APPROVE" else "CLOSED"
        topic.reviewed_by = actor.id
        topic.reviewed_at = _now()
        topic.review_note = cleaned
        await self.session.flush()
        await events.publish(
            self.session,
            events.TopicReviewed(topic_id=topic.id, approved=decision == "APPROVE"),
        )
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    # ── رزرو ───────────────────────────────────────────────────────────
    async def reserve(self, *, topic_id: uuid.UUID, actor: CurrentUser) -> ResearchTopic:
        if not await authz.has_permission(self.session, actor, Permission.RESEARCH_PARTICIPATE):
            raise PermissionDenied(
                "رزرو موضوع برای دانشجویان است.",
                permission=Permission.RESEARCH_PARTICIPATE.value,
            )
        topic = await self.require(topic_id, actor)
        held = await self.session.scalar(
            select(ResearchTopic.id).where(
                ResearchTopic.reserved_by == actor.id, ResearchTopic.status == "RESERVED"
            )
        )
        if held is not None and held != topic.id:
            raise ReservationLimit

        now = _now()
        try:
            async with self.session.begin_nested():
                won = await self.session.scalar(
                    update(ResearchTopic)
                    .where(ResearchTopic.id == topic.id, ResearchTopic.status == "OPEN")
                    .values(
                        status="RESERVED",
                        reserved_by=actor.id,
                        reserved_at=now,
                        last_activity_at=now,
                    )
                    .returning(ResearchTopic.id)
                    .execution_options(synchronize_session=False)
                )
        except IntegrityError as exc:
            # رزرو هم‌زمان دیگری از خود همین کاربر — ایندکس یکتا.
            raise ReservationLimit from exc
        await self.session.refresh(topic)
        if won is None:
            if topic.status in ("RESERVED", "TAKEN"):
                raise TopicAlreadyReserved
            raise Conflict("این موضوع برای رزرو باز نیست.")
        await self.session.commit()
        await self.session.refresh(topic)
        log.info("topic_reserved", topic_id=str(topic.id))
        return topic

    async def release(self, *, topic: ResearchTopic, actor: CurrentUser) -> ResearchTopic:
        """رزروکننده یا کادر. موضوع در حال انجام را فقط کادر باز می‌کند (`reopen`)."""
        if topic.status != "RESERVED":
            raise Conflict("این موضوع رزرو نیست.")
        if topic.reserved_by != actor.id:
            await self._require_manager(actor)
        self._clear_reservation(topic, "OPEN")
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    async def close(
        self, *, topic: ResearchTopic, actor: CurrentUser, reason: str | None
    ) -> ResearchTopic:
        await self._require_manager(actor)
        if topic.status == "CLOSED":
            raise Conflict("این موضوع قبلاً بسته شده است.")
        cleaned = self._note(reason)
        if cleaned is None:
            raise ValidationFailed("برای بستن موضوع دلیل بنویس.")
        self._clear_reservation(topic, "CLOSED")
        topic.review_note = cleaned
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    async def reopen(self, *, topic: ResearchTopic, actor: CurrentUser) -> ResearchTopic:
        """بسته یا در حال انجام ← باز. پژوهشی که رها شد، موضوعش به بانک برمی‌گردد."""
        await self._require_manager(actor)
        if topic.status not in ("CLOSED", "TAKEN"):
            raise Conflict("فقط موضوع بسته یا در حال انجام دوباره باز می‌شود.")
        self._clear_reservation(topic, "OPEN")
        topic.review_note = None
        await self.session.commit()
        await self.session.refresh(topic)
        return topic

    # ── تحرک — از `ResearchService` ───────────────────────────────────
    @staticmethod
    def touch(topic: ResearchTopic) -> None:
        """تحویل یا بازخورد — ساعت بی‌تحرکی رزرو از نو. فراخوان commit می‌کند."""
        if topic.status == "RESERVED":
            topic.last_activity_at = _now()

    @staticmethod
    def mark_taken(topic: ResearchTopic, user_id: uuid.UUID) -> None:
        """سطح ۱ روی این موضوع تأیید شد — کار واقعاً شروع شده است."""
        if topic.status == "RESERVED" and topic.reserved_by == user_id:
            topic.status = "TAKEN"
            topic.last_activity_at = _now()

    # ── کار شبانه — §7.11 `release_stale_topics` ───────────────────────
    async def release_stale(self, *, now: datetime | None = None) -> StaleStats:
        """هشدار روز ۲۵ و آزادسازی روز ۳۰. بی‌اثر در تکرار (`dedup_key`)."""
        moment = now or _now()
        release_before = moment - timedelta(days=rules.RESERVATION_IDLE_DAYS)
        warn_before = moment - timedelta(days=rules.RESERVATION_WARNING_DAYS)
        notifications = NotificationService(self.session)

        stale = list(
            await self.session.scalars(
                select(ResearchTopic)
                .where(
                    ResearchTopic.status == "RESERVED",
                    ResearchTopic.last_activity_at < release_before,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for topic in stale:
            holder = topic.reserved_by
            assert holder is not None
            reserved_at = topic.reserved_at
            self._clear_reservation(topic, "OPEN")
            await notifications.notify(
                "TOPIC_RELEASED",
                [holder],
                {"topic": topic.title, "days": str(rules.RESERVATION_IDLE_DAYS)},
                action_url=f"/research/topics/{topic.id}",
                dedup_key=f"TOPIC_RELEASED:{topic.id}:{reserved_at.isoformat() if reserved_at else ''}",  # noqa: E501
            )

        warned = 0
        for topic in await self.session.scalars(
            select(ResearchTopic).where(
                ResearchTopic.status == "RESERVED",
                ResearchTopic.last_activity_at < warn_before,
                ResearchTopic.last_activity_at >= release_before,
            )
        ):
            assert topic.reserved_by is not None and topic.last_activity_at is not None
            left = rules.RESERVATION_IDLE_DAYS - (moment - topic.last_activity_at).days
            created = await notifications.notify(
                "TOPIC_RELEASE_WARNING",
                [topic.reserved_by],
                {"topic": topic.title, "days": str(max(left, 1))},
                action_url="/research",
                # یک هشدار برای هر دورهٔ بی‌تحرکی — تحرک تازه دورهٔ تازه است.
                dedup_key=f"TOPIC_RELEASE_WARNING:{topic.id}:{topic.last_activity_at.isoformat()}",
            )
            warned += len(created)

        await self.session.commit()
        if stale or warned:
            log.info("stale_topics", released=len(stale), warned=warned)
        return StaleStats(warned=warned, released=len(stale))

    # ── درونی ──────────────────────────────────────────────────────────
    @staticmethod
    def _clear_reservation(topic: ResearchTopic, status: str) -> None:
        topic.status = status
        topic.reserved_by = None
        topic.reserved_at = None
        topic.last_activity_at = None

    @staticmethod
    def _note(value: str | None) -> str | None:
        cleaned = _clean(value)
        if cleaned is not None and len(cleaned) > NOTE_MAX:
            raise ValidationFailed(f"یادداشت حداکثر {NOTE_MAX} نویسه است.")
        return cleaned

    @staticmethod
    def _apply(topic: ResearchTopic, draft: TopicDraft) -> None:
        title = " ".join(draft.title.split())
        description = draft.description.strip()
        prerequisites = _clean(draft.prerequisites)
        if not 5 <= len(title) <= TOPIC_TITLE_MAX:
            raise ValidationFailed(f"عنوان موضوع باید بین ۵ تا {TOPIC_TITLE_MAX} نویسه باشد.")
        if not 20 <= len(description) <= TOPIC_DESCRIPTION_MAX:
            raise ValidationFailed("شرح موضوع دست‌کم ۲۰ نویسه باشد.")
        if prerequisites is not None and len(prerequisites) > PREREQUISITES_MAX:
            raise ValidationFailed(f"پیش‌نیازها حداکثر {PREREQUISITES_MAX} نویسه است.")
        if draft.level is not None and draft.level not in rules.LEVELS:
            raise ValidationFailed("سطح پیشنهادی باید بین ۱ تا ۴ باشد.")
        topic.title = title
        topic.description = description
        topic.prerequisites = prerequisites
        topic.level = draft.level


__all__ = ["REVIEW_DECISIONS", "StaleStats", "TopicDraft", "TopicService"]
