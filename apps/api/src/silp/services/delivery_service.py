"""مرحله و تحویل‌دادنی — FR-PRJ-05، §7.6، §7.12.

چهار قاعده که هیچ‌کدام قابل مذاکره نیستند:

۱. **نسخه‌ها هرگز پاک نمی‌شوند.** «اصلاح کن» یعنی نسخهٔ بعدی، نه
   بازنویسی نسخهٔ قبلی.
۲. **`CHANGES_REQUESTED` و `REJECTED` بدون بازخورد متنی پذیرفته
   نمی‌شوند** — در سرویس و در قید دیتابیس، هر دو.
۳. **تحویل پس از مهلت مجاز است** ولی `is_late` می‌خورد؛ بستن در فرد
   کار را متوقف می‌کند، علامت‌گذاری نه.
۴. **شمارهٔ نسخه با قید یکتا و تلاش مجدد گرفته می‌شود**، نه
   `SELECT MAX(...) + 1` خام (§7.12).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    ConcurrentModification,
    Conflict,
    MilestoneNotOpen,
    NotFound,
    NotTeamMember,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser
from silp.models.delivery import (
    DELIVERABLE_STATUSES,
    FEEDBACK_REQUIRED_STATUSES,
    OUTPUT_KINDS,
    Deliverable,
    DeliverableFile,
    Milestone,
)
from silp.models.project import Project
from silp.services import events
from silp.services.project_service import MAX_MILESTONES_PER_PROJECT, ProjectService

log = get_logger("silp.delivery")

VERSION_ATTEMPTS = 3
MAX_LINKS_PER_DELIVERABLE = 10
MAX_LINK_LENGTH = 500
REVIEW_DECISIONS = ("APPROVED", "CHANGES_REQUESTED", "REJECTED")

# وضعیت‌هایی که یعنی «این عضو تحویل بازی دارد و نباید نسخهٔ تازه بفرستد».
OPEN_DELIVERABLE_STATUSES = ("SUBMITTED", "UNDER_REVIEW")


@dataclass(slots=True)
class MilestoneDraft:
    title_fa: str
    description: str | None = None
    sort_order: int = 0
    due_on: date | None = None
    points: Decimal | float = 0
    is_required: bool = True
    output_kind: str | None = None
    checklist: list[str] | None = None


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    deliverable: Deliverable
    milestone: Milestone
    # آیا با این تأیید، همهٔ مراحل الزامی تمام شد؟ — §7.6 «پیشنهاد بستن پروژه»
    project_ready_to_close: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


class DeliveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    # ── مرحله ──────────────────────────────────────────────────────────
    async def milestones(self, project_id: uuid.UUID) -> list[Milestone]:
        rows = await self.session.scalars(
            select(Milestone)
            .where(Milestone.project_id == project_id)
            .order_by(Milestone.sort_order, Milestone.created_at)
        )
        return list(rows)

    async def require_milestone(self, milestone_id: uuid.UUID) -> Milestone:
        milestone = await self.session.get(Milestone, milestone_id)
        if milestone is None:
            raise NotFound("این مرحله پیدا نشد.")
        return milestone

    async def create_milestone(
        self, *, project: Project, actor: CurrentUser, draft: MilestoneDraft
    ) -> Milestone:
        _validate_milestone(draft)
        count = (
            await self.session.scalar(
                select(func.count())
                .select_from(Milestone)
                .where(Milestone.project_id == project.id)
            )
            or 0
        )
        if count >= MAX_MILESTONES_PER_PROJECT:
            raise ValidationFailed(f"هر پروژه حداکثر {MAX_MILESTONES_PER_PROJECT} مرحله دارد.")

        milestone = Milestone(
            project_id=project.id,
            title_fa=draft.title_fa.strip(),
            description=(draft.description or "").strip() or None,
            sort_order=draft.sort_order,
            due_on=draft.due_on,
            points=Decimal(str(draft.points)),
            is_required=draft.is_required,
            output_kind=draft.output_kind,
            checklist=list(draft.checklist or []),
            # مرحلهٔ پروژه‌ای که کارش شروع شده، از همان ابتدا باز است.
            status="IN_PROGRESS" if project.status == "IN_PROGRESS" else "PENDING",
        )
        self.session.add(milestone)
        await self.projects.record_activity(
            project,
            actor.id,
            "MILESTONE_ADDED",
            f"مرحلهٔ «{milestone.title_fa}» تعریف شد.",
            entity_type="milestone",
            commit=False,
        )
        await self.session.commit()
        return milestone

    async def update_milestone(
        self, *, milestone: Milestone, project: Project, actor: CurrentUser, draft: MilestoneDraft
    ) -> Milestone:
        _validate_milestone(draft)
        if milestone.status == "APPROVED":
            raise Conflict("مرحلهٔ تأییدشده ویرایش نمی‌شود.")
        milestone.title_fa = draft.title_fa.strip()
        milestone.description = (draft.description or "").strip() or None
        milestone.sort_order = draft.sort_order
        milestone.due_on = draft.due_on
        milestone.points = Decimal(str(draft.points))
        milestone.is_required = draft.is_required
        milestone.output_kind = draft.output_kind
        milestone.checklist = list(draft.checklist or [])
        await self.projects.record_activity(
            project,
            actor.id,
            "MILESTONE_UPDATED",
            f"مرحلهٔ «{milestone.title_fa}» به‌روز شد.",
            entity_type="milestone",
            entity_id=milestone.id,
            commit=False,
        )
        await self.session.commit()
        return milestone

    async def delete_milestone(self, *, milestone: Milestone, project: Project) -> None:
        """حذف مرحله فقط تا وقتی هیچ تحویلی برایش نیامده باشد."""
        submitted = await self.session.scalar(
            select(func.count())
            .select_from(Deliverable)
            .where(Deliverable.milestone_id == milestone.id)
        )
        if submitted:
            raise Conflict("برای این مرحله تحویل ثبت شده است؛ حذف نمی‌شود.")
        await self.session.delete(milestone)
        project.last_activity_at = _now()
        await self.session.commit()

    # ── تحویل‌دادنی ────────────────────────────────────────────────────
    async def deliverables(self, milestone_id: uuid.UUID) -> list[Deliverable]:
        rows = await self.session.scalars(
            select(Deliverable)
            .where(Deliverable.milestone_id == milestone_id)
            .order_by(Deliverable.submitted_at, Deliverable.version)
        )
        return list(rows)

    async def require_deliverable(self, deliverable_id: uuid.UUID) -> Deliverable:
        deliverable = await self.session.get(Deliverable, deliverable_id)
        if deliverable is None:
            raise NotFound("این تحویل‌دادنی پیدا نشد.")
        return deliverable

    async def submit(
        self,
        *,
        milestone: Milestone,
        project: Project,
        actor: CurrentUser,
        body: str | None,
        links: list[str] | None = None,
        file_ids: list[uuid.UUID] | None = None,
    ) -> Deliverable:
        """§7.6 — ارسال یک نسخهٔ تازه برای یک مرحله."""
        if await self.projects.membership(project.id, actor.id) is None:
            raise NotTeamMember
        if project.status not in ("IN_PROGRESS", "OPEN"):
            raise MilestoneNotOpen("پروژه در وضعیتی نیست که تحویل بپذیرد.")
        if not milestone.accepts_submission:
            raise MilestoneNotOpen("این مرحله تأیید شده است و تحویل تازه نمی‌پذیرد.")

        text = (body or "").strip() or None
        cleaned_links = _validate_links(links)
        if not text and not cleaned_links and not file_ids:
            raise ValidationFailed("تحویل‌دادنی خالی نمی‌شود؛ متن، فایل یا لینک بگذارید.")

        previous = await self.session.scalar(
            select(Deliverable)
            .where(
                Deliverable.milestone_id == milestone.id,
                Deliverable.submitter_id == actor.id,
            )
            .order_by(Deliverable.version.desc())
            .limit(1)
        )
        if previous is not None and previous.status in OPEN_DELIVERABLE_STATUSES:
            raise Conflict("نسخهٔ قبلی شما هنوز در انتظار بررسی است.")
        if previous is not None and previous.status == "APPROVED":
            raise Conflict("تحویل شما برای این مرحله تأیید شده است.")

        now = _now()
        is_late = milestone.due_on is not None and now.date() > milestone.due_on
        next_version = (previous.version + 1) if previous else 1

        deliverable = await self._insert_with_version(
            milestone_id=milestone.id,
            submitter_id=actor.id,
            first_version=next_version,
            body=text,
            links=cleaned_links,
            is_late=is_late,
        )

        for file_id in file_ids or []:
            self.session.add(DeliverableFile(deliverable_id=deliverable.id, file_id=file_id))

        if milestone.status in ("PENDING", "IN_PROGRESS", "OVERDUE"):
            milestone.status = "SUBMITTED"
        await self.projects.record_activity(
            project,
            actor.id,
            "DELIVERABLE_SUBMITTED",
            f"نسخهٔ {deliverable.version} مرحلهٔ «{milestone.title_fa}» تحویل شد.",
            entity_type="deliverable",
            entity_id=deliverable.id,
            commit=False,
        )
        await self.session.commit()
        log.info(
            "deliverable_submitted",
            deliverable_id=str(deliverable.id),
            version=deliverable.version,
            late=is_late,
        )
        return deliverable

    async def start_review(self, *, deliverable: Deliverable) -> Deliverable:
        """`SUBMITTED → UNDER_REVIEW` — بازبین بازش کرد."""
        if deliverable.status == "SUBMITTED":
            deliverable.status = "UNDER_REVIEW"
            await self.session.commit()
        return deliverable

    async def review(
        self,
        *,
        deliverable: Deliverable,
        actor: CurrentUser,
        decision: str,
        feedback: str | None = None,
        score: Decimal | float | None = None,
        rubric_scores: dict[str, Any] | None = None,
    ) -> ReviewOutcome:
        """§7.6 — تصمیم بازبین. بازخورد برای رد و اصلاح اجباری است."""
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("تصمیم بررسی معتبر نیست.")
        if not deliverable.is_open_for_review:
            raise Conflict("این تحویل‌دادنی قبلاً بررسی شده است.")

        text = (feedback or "").strip() or None
        if decision in FEEDBACK_REQUIRED_STATUSES and not text:
            raise ValidationFailed(
                "برای «اصلاح کن» یا «رد»، نوشتن بازخورد اجباری است؛"
                " دانشجو باید بداند چه چیزی را درست کند."
            )
        if actor.id == deliverable.submitter_id:
            raise Conflict("تحویل خودتان را نمی‌توانید بررسی کنید.")

        milestone = await self.require_milestone(deliverable.milestone_id)
        project = await self.projects.require(milestone.project_id)

        deliverable.status = decision
        deliverable.feedback = text
        deliverable.score = None if score is None else Decimal(str(score))
        deliverable.rubric_scores = rubric_scores
        deliverable.reviewed_by = actor.id
        deliverable.reviewed_at = _now()

        ready = False
        if decision == "APPROVED":
            milestone.status = "APPROVED"
            milestone.approved_at = _now()
            ready = await self._all_required_approved(project.id)
        else:
            # مرحله به حالت کاری برمی‌گردد تا نسخهٔ بعدی جا داشته باشد.
            milestone.status = "IN_PROGRESS"
            milestone.approved_at = None

        await self.projects.record_activity(
            project,
            actor.id,
            "DELIVERABLE_REVIEWED",
            _review_summary(decision, milestone.title_fa),
            entity_type="deliverable",
            entity_id=deliverable.id,
            commit=False,
        )
        await events.publish(
            self.session,
            events.DeliverableReviewed(
                deliverable_id=deliverable.id, reviewer_id=actor.id, decision=decision
            ),
        )
        await self.session.commit()
        log.info("deliverable_reviewed", deliverable_id=str(deliverable.id), decision=decision)
        return ReviewOutcome(
            deliverable=deliverable, milestone=milestone, project_ready_to_close=ready
        )

    async def review_queue(self, project_id: uuid.UUID) -> list[Deliverable]:
        """صف بررسی یک پروژه — قدیمی‌ترین اول."""
        rows = await self.session.scalars(
            select(Deliverable)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(
                Milestone.project_id == project_id,
                Deliverable.status.in_(OPEN_DELIVERABLE_STATUSES),
            )
            .order_by(Deliverable.submitted_at, Deliverable.id)
        )
        return list(rows)

    # ── درونی ──────────────────────────────────────────────────────────
    async def _insert_with_version(
        self,
        *,
        milestone_id: uuid.UUID,
        submitter_id: uuid.UUID,
        first_version: int,
        body: str | None,
        links: list[str],
        is_late: bool,
    ) -> Deliverable:
        """§7.12 — قید یکتا + تلاش مجدد، نه `MAX(version) + 1` خام."""
        version = first_version
        for attempt in range(VERSION_ATTEMPTS):
            deliverable = Deliverable(
                milestone_id=milestone_id,
                submitter_id=submitter_id,
                version=version,
                body=body,
                links=links,
                is_late=is_late,
                status="SUBMITTED",
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(deliverable)
                    await self.session.flush()
            except IntegrityError:
                if attempt == VERSION_ATTEMPTS - 1:
                    raise ConcurrentModification from None
                # کس دیگری (یا کلیک دوم خودِ کاربر) همین شماره را گرفت.
                highest = await self.session.scalar(
                    select(func.max(Deliverable.version)).where(
                        Deliverable.milestone_id == milestone_id,
                        Deliverable.submitter_id == submitter_id,
                    )
                )
                version = (highest or 0) + 1
                continue
            return deliverable
        raise ConcurrentModification

    async def _all_required_approved(self, project_id: uuid.UUID) -> bool:
        """§7.6 — آیا همهٔ مراحل الزامی تأیید شده‌اند؟

        `flush` صریح لازم است: نشست اپ `autoflush=False` دارد (D-01)، پس
        وضعیت تازهٔ مرحله که هنوز در حافظه است، در این `SELECT` دیده
        نمی‌شود و نتیجه همیشه «هنوز نه» می‌شود.
        """
        await self.session.flush()
        pending = await self.session.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(
                Milestone.project_id == project_id,
                Milestone.is_required.is_(True),
                Milestone.status != "APPROVED",
            )
        )
        total_required = await self.session.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(Milestone.project_id == project_id, Milestone.is_required.is_(True))
        )
        return bool(total_required) and not pending


def _review_summary(decision: str, milestone_title: str) -> str:
    match decision:
        case "APPROVED":
            return f"مرحلهٔ «{milestone_title}» تأیید شد."
        case "CHANGES_REQUESTED":
            return f"برای مرحلهٔ «{milestone_title}» اصلاح خواسته شد."
        case _:
            return f"تحویل مرحلهٔ «{milestone_title}» رد شد."


def _validate_milestone(draft: MilestoneDraft) -> None:
    if not draft.title_fa.strip():
        raise ValidationFailed("عنوان مرحله را خالی نگذارید.")
    if draft.output_kind is not None and draft.output_kind not in OUTPUT_KINDS:
        raise ValidationFailed("نوع خروجی مرحله معتبر نیست.")
    if Decimal(str(draft.points)) < 0:
        raise ValidationFailed("بارم امتیاز منفی نمی‌شود.")


def _validate_links(links: list[str] | None) -> list[str]:
    cleaned = [link.strip() for link in (links or []) if link.strip()]
    if len(cleaned) > MAX_LINKS_PER_DELIVERABLE:
        raise ValidationFailed(f"حداکثر {MAX_LINKS_PER_DELIVERABLE} لینک.")
    for link in cleaned:
        if len(link) > MAX_LINK_LENGTH:
            raise ValidationFailed("یکی از لینک‌ها بیش از حد بلند است.")
        if not link.startswith(("http://", "https://")):
            raise ValidationFailed("لینک باید با http:// یا https:// شروع شود.")
    return cleaned


__all__ = [
    "DELIVERABLE_STATUSES",
    "MAX_LINKS_PER_DELIVERABLE",
    "OPEN_DELIVERABLE_STATUSES",
    "REVIEW_DECISIONS",
    "DeliveryService",
    "MilestoneDraft",
    "ReviewOutcome",
]
