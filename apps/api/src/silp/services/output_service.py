"""خروجی‌های پژوهشی — FR-RES-02، ADR-0015.

نویسنده وضعیت مقاله را خودش به‌روز می‌کند (پیش‌نویس ← ارسال ← … ←
منتشرشده). هر ویرایشی که امتیاز `OUTPUT_*` را عوض کند — مرحلهٔ تازه، یا
چارک دیگر — خروجی را به صف راستی‌آزمایی می‌فرستد (`review_status =
PENDING`). بازبین DOI، ایمیل پذیرش یا صفحهٔ مجله را می‌بیند و «راستی‌آزمایی»
یا «رد» می‌کند؛ امتیاز فقط از راستی‌آزمایی می‌آید.

خروجی‌ای که یک‌بار راستی‌آزمایی شده حذف نمی‌شود: امتیازش در دفتر کل است
و ردیف منبعش باید بماند. اصلاحش همان مسیر صف است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    NotFound,
    PermissionDenied,
    UploadIncomplete,
    ValidationFailed,
)
from silp.core.permissions import CurrentUser, Permission
from silp.domain import research as rules
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.models.file import File
from silp.models.project import Team, TeamMember
from silp.models.research import (
    AUTHORS_MAX,
    NOTE_MAX,
    OUTPUT_TITLE_MAX,
    ResearchOutput,
)
from silp.services import authz, events

REVIEW_DECISIONS = ("VERIFIED", "REJECTED")
QUEUE_LIMIT = 200
VENUE_MAX = 300


@dataclass(slots=True)
class OutputDraft:
    kind: str
    title: str
    authors: str
    status: str = "DRAFT"
    venue: str | None = None
    quartile: str | None = None
    doi: str | None = None
    url: str | None = None
    file_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    submitted_on: date | None = None
    published_on: date | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    cleaned = " ".join((value or "").split())
    return cleaned or None


class OutputService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── خواندن ─────────────────────────────────────────────────────────
    async def mine(self, owner_id: uuid.UUID) -> list[ResearchOutput]:
        rows = await self.session.scalars(
            select(ResearchOutput)
            .where(ResearchOutput.owner_id == owner_id)
            .order_by(ResearchOutput.created_at.desc())
        )
        return list(rows)

    async def require_own(self, output_id: uuid.UUID, actor: CurrentUser) -> ResearchOutput:
        output = await self.session.get(ResearchOutput, output_id)
        if output is None or output.owner_id != actor.id:
            raise NotFound("این خروجی پیدا نشد.")
        return output

    async def can_review(self, actor: CurrentUser) -> bool:
        return await authz.has_permission(self.session, actor, Permission.RESEARCH_REVIEW)

    # ── ثبت و ویرایش ───────────────────────────────────────────────────
    async def create(self, *, actor: CurrentUser, draft: OutputDraft) -> ResearchOutput:
        output = ResearchOutput(owner_id=actor.id)
        await self._apply(output, draft, actor)
        self._refresh_review_status(output)
        self.session.add(output)
        await self.session.commit()
        await self.session.refresh(output)
        return output

    async def update(
        self, *, output: ResearchOutput, actor: CurrentUser, draft: OutputDraft
    ) -> ResearchOutput:
        await self._apply(output, draft, actor)
        self._refresh_review_status(output)
        await self.session.commit()
        await self.session.refresh(output)
        return output

    async def delete(self, *, output: ResearchOutput) -> None:
        if output.verified_stage is not None:
            raise Conflict("خروجی راستی‌آزمایی‌شده حذف نمی‌شود؛ اگر اشتباهی هست، ویرایشش کن.")
        await self.session.delete(output)
        await self.session.commit()

    # ── راستی‌آزمایی ───────────────────────────────────────────────────
    async def review_queue(self, actor: CurrentUser) -> list[ResearchOutput]:
        await self._require_reviewer(actor)
        rows = await self.session.scalars(
            select(ResearchOutput)
            .where(ResearchOutput.review_status == "PENDING", ResearchOutput.owner_id != actor.id)
            .order_by(ResearchOutput.updated_at)
            .limit(QUEUE_LIMIT)
        )
        return list(rows)

    async def review(
        self,
        *,
        output_id: uuid.UUID,
        actor: CurrentUser,
        decision: str,
        note: str | None = None,
    ) -> ResearchOutput:
        await self._require_reviewer(actor)
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        output = await self.session.scalar(
            select(ResearchOutput).where(ResearchOutput.id == output_id).with_for_update()
        )
        if output is None:
            raise NotFound("این خروجی پیدا نشد.")
        if output.owner_id == actor.id:
            raise PermissionDenied("خروجی خودت را نمی‌توانی راستی‌آزمایی کنی.")
        if output.review_status != "PENDING":
            raise Conflict("این خروجی در انتظار راستی‌آزمایی نیست.")
        cleaned = _clean(note)
        if decision == "REJECTED" and cleaned is None:
            raise ValidationFailed("برای رد، بنویس چه شاهدی کم است.")
        if cleaned is not None and len(cleaned) > NOTE_MAX:
            raise ValidationFailed(f"یادداشت حداکثر {NOTE_MAX} نویسه است.")

        if decision == "VERIFIED":
            output.verified_stage = rules.stage_of(output.status)
            output.verified_quartile = rules.effective_quartile(output.kind, output.quartile)
        output.review_status = decision
        output.reviewed_by = actor.id
        output.reviewed_at = _now()
        output.review_note = cleaned
        await self.session.flush()
        await events.publish(self.session, events.OutputReviewed(output_id=output.id))
        await self.session.commit()
        await self.session.refresh(output)
        return output

    # ── درونی ──────────────────────────────────────────────────────────
    @staticmethod
    def _refresh_review_status(output: ResearchOutput) -> None:
        pending = rules.needs_review(
            kind=output.kind,
            status=output.status,
            quartile=output.quartile,
            verified_stage=output.verified_stage,
            verified_quartile=output.verified_quartile,
        )
        if pending:
            output.review_status = "PENDING"
            output.review_note = None
        elif output.review_status in ("PENDING", "REJECTED"):
            # ادعا به همان چیزی برگشت که تأیید شده بود، یا هنوز ادعایی نیست.
            output.review_status = "VERIFIED" if output.verified_stage else "NONE"

    async def _apply(self, output: ResearchOutput, draft: OutputDraft, actor: CurrentUser) -> None:
        if draft.kind not in rules.OUTPUT_KINDS:
            raise ValidationFailed("نوع خروجی معتبر نیست.")
        if draft.status not in rules.OUTPUT_STATUSES:
            raise ValidationFailed("وضعیت خروجی معتبر نیست.")
        if draft.quartile is not None and draft.quartile not in rules.QUARTILES:
            raise ValidationFailed("چارک معتبر نیست.")
        title = _clean(draft.title) or ""
        authors = _clean(draft.authors) or ""
        if not 3 <= len(title) <= OUTPUT_TITLE_MAX:
            raise ValidationFailed(f"عنوان باید بین ۳ تا {OUTPUT_TITLE_MAX} نویسه باشد.")
        if not 2 <= len(authors) <= AUTHORS_MAX:
            raise ValidationFailed("نام نویسندگان را بنویس.")
        venue = _clean(draft.venue)
        if venue is not None and len(venue) > VENUE_MAX:
            raise ValidationFailed(f"نام مجله یا کنفرانس حداکثر {VENUE_MAX} نویسه است.")

        doi = rules.normalize_doi(draft.doi)
        if doi is not None and not rules.is_doi(doi):
            raise ValidationFailed(
                "DOI معتبر نیست؛ باید با «10.» شروع شود، مثل 10.1016/j.aap.2024.1."
            )
        url = (draft.url or "").strip() or None
        if url is not None and not rules.is_url(url):
            raise ValidationFailed("پیوند باید با http:// یا https:// شروع شود.")

        today = _now().astimezone(LOCAL_TZ).date()
        for when in (draft.submitted_on, draft.published_on):
            if when is not None and when > today:
                raise ValidationFailed("تاریخ ارسال یا انتشار نمی‌تواند در آینده باشد.")
        if (
            draft.submitted_on is not None
            and draft.published_on is not None
            and draft.published_on < draft.submitted_on
        ):
            raise ValidationFailed("تاریخ انتشار پیش از تاریخ ارسال است.")

        if draft.file_id is not None and draft.file_id != output.file_id:
            await self._require_file(draft.file_id, actor.id)
        if draft.project_id is not None and draft.project_id != output.project_id:
            await self._require_project_member(draft.project_id, actor.id)

        output.kind = draft.kind
        output.title = title
        output.authors = authors
        output.venue = venue
        output.quartile = draft.quartile if draft.kind == "JOURNAL" else None
        output.status = draft.status
        output.doi = doi
        output.url = url
        output.file_id = draft.file_id
        output.project_id = draft.project_id
        output.submitted_on = draft.submitted_on
        output.published_on = draft.published_on

    async def _require_file(self, file_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        file = await self.session.get(File, file_id)
        if file is None or file.uploaded_by != owner_id or file.deleted_at is not None:
            raise NotFound("فایل پیدا نشد.")
        if not file.is_attachable:
            raise UploadIncomplete

    async def _require_project_member(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """پروژه‌ای که خروجی از آن آمده — عضو فعلی یا پیشین آن تیم."""
        found = await self.session.scalar(
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.project_id == project_id,
                TeamMember.user_id == user_id,
                TeamMember.status.in_(("ACTIVE", "LEFT")),
            )
            .limit(1)
        )
        if found is None:
            raise NotFound("پروژه پیدا نشد یا عضوش نبوده‌ای.")

    async def _require_reviewer(self, actor: CurrentUser) -> None:
        if not await self.can_review(actor):
            raise PermissionDenied(
                "راستی‌آزمایی خروجی پژوهشی با منتور، استاد یا مدیر آموزشی است.",
                permission=Permission.RESEARCH_REVIEW.value,
            )


__all__ = ["REVIEW_DECISIONS", "OutputDraft", "OutputService"]
