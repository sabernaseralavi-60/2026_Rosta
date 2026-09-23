"""مسیر پژوهش چهارسطحی — FR-RES-01، M7-05، ADR-0015.

## چرخه

```
سطح بی‌ردیف ──تحویل──► SUBMITTED ──تأیید──► APPROVED ─► ردیف سطح بعد IN_PROGRESS
                          │
                          └─اصلاح کن─► IN_PROGRESS ──تحویل (نسخهٔ بعد)──► SUBMITTED
```

* فقط «سطح جاری» تحویل می‌پذیرد: اولین سطحی که تأیید نشده. سطح ۲ بدون
  تأیید سطح ۱ قفل است (FR-RES-01 «ارتقا نیازمند تأیید سطح فعلی است»).
* هر تحویل یک نسخه است و نسخهٔ قبلی با بازخوردش می‌ماند (الگوی §7.6).
* بازبین هر کسی با `research.review` است جز خود دانشجو. نخستین بازبین
  «منتور» سطح ثبت می‌شود و تحویل بعدی به او خبر داده می‌شود.
* تأیید سطح ۱ روی موضوعی از بانک موضوع، آن موضوع را از «رزرو» به «در حال
  انجام» می‌برد — دیگر با بی‌تحرکی آزاد نمی‌شود (FR-RES-03).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import research as rules
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.models.research import (
    ResearchSubmission,
    ResearchSubmissionFile,
    ResearchTrack,
)
from silp.services import authz, events
from silp.services.topic_service import TopicService

log = get_logger("silp.research")

REVIEW_DECISIONS = ("APPROVED", "CHANGES_REQUESTED")
QUEUE_LIMIT = 200
FEEDBACK_MAX = 2000


def _now() -> datetime:
    return datetime.now(UTC)


class ResearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.topics = TopicService(session)

    # ── خواندن ─────────────────────────────────────────────────────────
    async def tracks(self, user_id: uuid.UUID) -> dict[int, ResearchTrack]:
        rows = await self.session.scalars(
            select(ResearchTrack).where(ResearchTrack.user_id == user_id)
        )
        return {row.level: row for row in rows}

    async def submissions(self, user_id: uuid.UUID) -> dict[int, list[ResearchSubmission]]:
        """نسخه‌های هر سطح — تازه‌ترین اول."""
        rows = await self.session.scalars(
            select(ResearchSubmission)
            .where(ResearchSubmission.user_id == user_id)
            .order_by(ResearchSubmission.level, ResearchSubmission.version.desc())
        )
        result: dict[int, list[ResearchSubmission]] = defaultdict(list)
        for row in rows:
            result[row.level].append(row)
        return dict(result)

    async def require_submission(self, submission_id: uuid.UUID) -> ResearchSubmission:
        row = await self.session.get(ResearchSubmission, submission_id)
        if row is None:
            raise NotFound("این تحویل پیدا نشد.")
        return row

    async def can_review(self, actor: CurrentUser) -> bool:
        return await authz.has_permission(self.session, actor, Permission.RESEARCH_REVIEW)

    async def require_visible(
        self, submission_id: uuid.UUID, actor: CurrentUser
    ) -> ResearchSubmission:
        """خود دانشجو یا بازبین. برای دیگران «وجود ندارد» — §6.4 قاعدهٔ ۴."""
        row = await self.require_submission(submission_id)
        if row.user_id != actor.id and not await self.can_review(actor):
            raise NotFound("این تحویل پیدا نشد.")
        return row

    # ── تحویل ──────────────────────────────────────────────────────────
    async def submit(
        self,
        *,
        actor: CurrentUser,
        level: int,
        summary: str,
        links: list[str],
        file_ids: list[uuid.UUID],
        evidence: dict[str, Any],
    ) -> ResearchSubmission:
        """تحویل سطح جاری. فایل‌ها را فراخوان پیش‌تر سنجیده است (`load_attachable`)."""
        if not await authz.has_permission(self.session, actor, Permission.RESEARCH_PARTICIPATE):
            raise PermissionDenied(
                "مسیر پژوهش برای دانشجویان است.",
                permission=Permission.RESEARCH_PARTICIPATE.value,
            )
        if level not in rules.LEVELS:
            raise NotFound("این سطح وجود ندارد.")

        if level == 1:
            # ردیف سطح ۱ با اولین تحویل ساخته می‌شود؛ دو تحویل هم‌زمان
            # هر دو «ساختن» را می‌بینند، پس درج بی‌اثر است و قفل بعدش.
            await self.session.execute(
                insert(ResearchTrack)
                .values(user_id=actor.id, level=1)
                .on_conflict_do_nothing(index_elements=["user_id", "level"])
            )
        track = await self.session.scalar(
            select(ResearchTrack)
            .where(ResearchTrack.user_id == actor.id, ResearchTrack.level == level)
            .with_for_update()
        )
        if track is None:
            raise Conflict("این سطح هنوز باز نشده است؛ اول سطح قبلی را تأیید بگیر.")
        if track.status == "APPROVED":
            raise Conflict("این سطح قبلاً تأیید شده است.")
        if track.status == "SUBMITTED":
            raise Conflict("تحویل قبلی این سطح هنوز در انتظار بررسی است.")

        # شاهدها پس از وضعیت سطح: سطح قفل باید «قفل» بگوید، نه «شاهد کم است».
        cleaned_links = list(dict.fromkeys(link.strip() for link in links if link.strip()))
        cleaned_summary = summary.strip()
        cleaned_evidence, problems = rules.validate_submission(
            level,
            summary=cleaned_summary,
            links=cleaned_links,
            file_count=len(set(file_ids)),
            evidence=evidence,
            today=_now().astimezone(LOCAL_TZ).date(),
        )
        if problems:
            raise ValidationFailed(
                "تحویل کامل نیست: " + "؛ ".join(problems) + ".",
                details={"missing": problems},
            )

        version = (
            await self.session.scalar(
                select(func.coalesce(func.max(ResearchSubmission.version), 0)).where(
                    ResearchSubmission.user_id == actor.id, ResearchSubmission.level == level
                )
            )
            or 0
        ) + 1
        topic = await self.topics.current_for(actor.id)
        submission = ResearchSubmission(
            user_id=actor.id,
            level=level,
            version=version,
            topic_id=topic.id if topic is not None else None,
            summary=cleaned_summary,
            links=cleaned_links,
            evidence=cleaned_evidence,
            status="SUBMITTED",
        )
        self.session.add(submission)
        await self.session.flush()
        for file_id in dict.fromkeys(file_ids):
            self.session.add(ResearchSubmissionFile(submission_id=submission.id, file_id=file_id))
        track.status = "SUBMITTED"
        if topic is not None:
            self.topics.touch(topic)
        await self.session.flush()
        await events.publish(self.session, events.ResearchSubmitted(submission_id=submission.id))
        await self.session.commit()
        await self.session.refresh(submission)
        log.info("research_submitted", level=level, version=version)
        return submission

    # ── بررسی ──────────────────────────────────────────────────────────
    async def review_queue(self, actor: CurrentUser) -> list[ResearchSubmission]:
        """تحویل‌های در انتظار، قدیمی‌ترین اول — جز تحویل خود بازبین."""
        await self._require_reviewer(actor)
        rows = await self.session.scalars(
            select(ResearchSubmission)
            .where(ResearchSubmission.status == "SUBMITTED", ResearchSubmission.user_id != actor.id)
            .order_by(ResearchSubmission.submitted_at)
            .limit(QUEUE_LIMIT)
        )
        return list(rows)

    async def review(
        self,
        *,
        submission_id: uuid.UUID,
        actor: CurrentUser,
        decision: str,
        feedback: str | None = None,
    ) -> ResearchSubmission:
        await self._require_reviewer(actor)
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        submission = await self.session.scalar(
            select(ResearchSubmission)
            .where(ResearchSubmission.id == submission_id)
            .with_for_update()
        )
        if submission is None:
            raise NotFound("این تحویل پیدا نشد.")
        if submission.user_id == actor.id:
            raise PermissionDenied("تحویل خودت را نمی‌توانی بررسی کنی.")
        if submission.status != "SUBMITTED":
            raise Conflict("این تحویل قبلاً بررسی شده است.")
        cleaned = (feedback or "").strip() or None
        if decision == "CHANGES_REQUESTED" and cleaned is None:
            raise ValidationFailed("برای درخواست اصلاح، بنویس چه چیزی باید عوض شود.")
        if cleaned is not None and len(cleaned) > FEEDBACK_MAX:
            raise ValidationFailed(f"بازخورد حداکثر {FEEDBACK_MAX} نویسه است.")

        now = _now()
        track = await self.session.scalar(
            select(ResearchTrack)
            .where(
                ResearchTrack.user_id == submission.user_id,
                ResearchTrack.level == submission.level,
            )
            .with_for_update()
        )
        assert track is not None  # کلید خارجی ترکیبی تضمینش می‌کند
        submission.status = decision
        submission.feedback = cleaned
        submission.reviewed_by = actor.id
        submission.reviewed_at = now
        if track.mentor_id is None:
            track.mentor_id = actor.id

        topic = (
            await self.topics.get(submission.topic_id) if submission.topic_id is not None else None
        )
        if decision == "APPROVED":
            track.status = "APPROVED"
            track.approved_at = now
            track.approved_by = actor.id
            if submission.level < rules.MAX_LEVEL:
                await self.session.execute(
                    insert(ResearchTrack)
                    .values(
                        user_id=submission.user_id,
                        level=submission.level + 1,
                        mentor_id=track.mentor_id,
                    )
                    .on_conflict_do_nothing(index_elements=["user_id", "level"])
                )
            if topic is not None and submission.level == 1:
                self.topics.mark_taken(topic, submission.user_id)
        else:
            track.status = "IN_PROGRESS"
            if topic is not None:
                self.topics.touch(topic)

        await self.session.flush()
        await events.publish(self.session, events.ResearchReviewed(submission_id=submission.id))
        await self.session.commit()
        await self.session.refresh(submission)
        log.info(
            "research_reviewed",
            submission_id=str(submission.id),
            level=submission.level,
            decision=decision,
        )
        return submission

    async def _require_reviewer(self, actor: CurrentUser) -> None:
        if not await self.can_review(actor):
            raise PermissionDenied(
                "بررسی مسیر پژوهش با منتور، استاد یا مدیر آموزشی است.",
                permission=Permission.RESEARCH_REVIEW.value,
            )


__all__ = ["REVIEW_DECISIONS", "ResearchService"]
