"""بانک ایده — FR-IDEA-01/02/03، §7.8، M7-01 و M7-02.

## دیده‌شدن

| وضعیت | فهرست عمومی | صفحهٔ ایده |
|-------|-------------|------------|
| `OPEN` | ✅ | ✅ |
| `PROMOTED` | ✅ (با فیلتر) | ✅ با پیوند به مقصد |
| `ARCHIVED` | ❌ | فقط نویسنده و ناظر |
| حذف‌شده | ❌ | ❌ |

## ناشناس

نام نویسندهٔ ایدهٔ ناشناس در هیچ پاسخی نیست — جز برای خودش. نویسنده در
سامانه ثبت است (امتیاز می‌گیرد و ناظر صاحب ایدهٔ توهین‌آمیز را می‌شناسد)،
ولی این شناسه از لایهٔ سرویس بیرون نمی‌رود؛ مسیرها `author_visible` را
می‌خوانند، نه `author_id` را.

## ارتقا (§7.8)

* **به پروژه:** استاد مدیر پروژهٔ `DRAFT` می‌شود؛ تیم همان لحظه ساخته
  می‌شود و نویسنده دعوت می‌گیرد — پذیرفتن، انتخاب خود اوست.
* **به کسب‌وکار:** نویسنده بنیان‌گذار می‌شود؛ ایده مال اوست. ایدهٔ ناشناس
  به کسب‌وکار ارتقا نمی‌یابد، چون صفحهٔ کسب‌وکار بنیان‌گذار را نشان
  می‌دهد و ارتقا ناشناسی را بی‌اجازه می‌شکست (ADR-0014).

همهٔ این‌ها در یک تراکنش: ایده‌ای که `PROMOTED` شده ولی مقصدش ساخته
نشده، یا برعکس، وجود ندارد.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Select, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from silp.core.exceptions import (
    Conflict,
    DuplicateVote,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import ideas as rules
from silp.models.idea import (
    BODY_MAX,
    COMMENT_MAX,
    IDEA_CATEGORIES,
    PROBLEM_MAX,
    TITLE_MAX,
    Idea,
    IdeaComment,
    IdeaVote,
)
from silp.models.project import PROJECT_KINDS
from silp.services import authz, events
from silp.services.invitation_service import InvitationService
from silp.services.project_service import ProjectDraft, ProjectService
from silp.services.venture_service import VentureDraft, VentureService

log = get_logger("silp.idea")

IDEA_SORTS = ("hot", "new", "top")
SUMMARY_MAX = 280


@dataclass(slots=True)
class IdeaDraft:
    title: str
    body: str
    problem: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_anonymous: bool = False


@dataclass(frozen=True, slots=True)
class Promotion:
    target_type: str
    target_id: uuid.UUID


def _now() -> datetime:
    return datetime.now(UTC)


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def hot_score_sql() -> ColumnElement[float | Decimal]:
    """همان `rules.hot_score` در SQL — `votes / (hours + 2) ^ 1.5`."""
    hours = func.extract("epoch", func.now() - Idea.created_at) / 3600.0
    return Idea.vote_count / func.power(
        func.greatest(hours, 0) + rules.HOT_OFFSET_HOURS, rules.HOT_GRAVITY
    )


class IdeaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── خواندن ─────────────────────────────────────────────────────────
    def list_query(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        status: str | None = "OPEN",
        author_id: uuid.UUID | None = None,
        sort: str = "hot",
    ) -> Select[tuple[Idea]]:
        stmt = select(Idea).where(Idea.deleted_at.is_(None))
        if author_id is not None:
            # «ایده‌های من» بایگانی‌شده را هم نشان می‌دهد.
            stmt = stmt.where(Idea.author_id == author_id)
        elif status:
            stmt = stmt.where(Idea.status == status)
        else:
            stmt = stmt.where(Idea.status != "ARCHIVED")
        if category:
            stmt = stmt.where(Idea.category == category)
        if tag and tag.strip():
            stmt = stmt.where(Idea.tags.contains([tag.strip()]))
        if q and q.strip():
            normalized = func.fa_normalize(q.strip())
            stmt = stmt.where(Idea.search_norm.like(func.concat("%", normalized, "%")))
        match sort:
            case "new":
                stmt = stmt.order_by(Idea.created_at.desc(), Idea.id.desc())
            case "top":
                stmt = stmt.order_by(Idea.vote_count.desc(), Idea.created_at.desc())
            case _:
                stmt = stmt.order_by(hot_score_sql().desc(), Idea.created_at.desc())
        return stmt

    async def page(
        self, stmt: Select[tuple[Idea]], *, offset: int, limit: int
    ) -> tuple[list[Idea], int]:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = await self.session.scalars(stmt.offset(offset).limit(limit))
        return list(rows), int(total)

    async def voted_by(self, user_id: uuid.UUID, idea_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not idea_ids:
            return set()
        rows = await self.session.scalars(
            select(IdeaVote.idea_id).where(
                IdeaVote.user_id == user_id, IdeaVote.idea_id.in_(idea_ids)
            )
        )
        return set(rows)

    async def get_visible(self, idea_id: uuid.UUID, viewer: CurrentUser | None) -> Idea:
        idea = await self.session.get(Idea, idea_id)
        if idea is None or idea.deleted_at is not None:
            raise NotFound("ایده پیدا نشد.")
        if idea.status == "ARCHIVED" and not (
            viewer is not None and (viewer.id == idea.author_id or await self.can_moderate(viewer))
        ):
            raise NotFound("ایده پیدا نشد.")
        return idea

    async def comments(self, idea_id: uuid.UUID) -> list[IdeaComment]:
        """نظرهای زنده، به‌علاوهٔ نظر ریشهٔ حذف‌شده‌ای که پاسخ زنده دارد.

        بدون آن، پاسخ‌ها بی‌والد می‌مانند و گفت‌وگو بی‌معنا می‌شود. متن
        نظر حذف‌شده را مسیر نشان نمی‌دهد (`is_deleted`).
        """
        rows = list(
            await self.session.scalars(
                select(IdeaComment)
                .where(IdeaComment.idea_id == idea_id)
                .order_by(IdeaComment.created_at, IdeaComment.id)
            )
        )
        live_parents = {c.parent_id for c in rows if c.deleted_at is None and c.parent_id}
        return [c for c in rows if c.deleted_at is None or c.id in live_parents]

    async def can_moderate(self, actor: CurrentUser) -> bool:
        return await authz.has_permission(self.session, actor, Permission.IDEA_MODERATE)

    async def can_promote(self, actor: CurrentUser) -> bool:
        return await authz.has_permission(self.session, actor, Permission.IDEA_PROMOTE)

    # ── نوشتن ──────────────────────────────────────────────────────────
    async def create(self, *, actor: CurrentUser, draft: IdeaDraft) -> Idea:
        idea = Idea(author_id=actor.id)
        self._apply(idea, draft)
        self.session.add(idea)
        await self.session.flush()
        await events.publish(self.session, events.IdeaSubmitted(idea_id=idea.id))
        await self.session.commit()
        await self.session.refresh(idea)
        log.info("idea_submitted", idea_id=str(idea.id))
        return idea

    async def update(self, *, idea: Idea, actor: CurrentUser, draft: IdeaDraft) -> Idea:
        if idea.author_id != actor.id:
            raise PermissionDenied("فقط نویسندهٔ ایده می‌تواند آن را ویرایش کند.")
        if idea.status != "OPEN":
            raise Conflict("ایدهٔ ارتقایافته یا بایگانی‌شده ویرایش نمی‌شود.")
        self._apply(idea, draft)
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    async def delete(self, *, idea: Idea, actor: CurrentUser) -> None:
        if idea.author_id != actor.id:
            raise PermissionDenied("فقط نویسندهٔ ایده می‌تواند آن را حذف کند.")
        if idea.status == "PROMOTED":
            raise Conflict("ایدهٔ ارتقایافته حذف نمی‌شود؛ پروژه یا کسب‌وکاری از آن ساخته شده.")
        idea.deleted_at = _now()
        await events.publish(self.session, events.IdeaWithdrawn(idea_id=idea.id))
        await self.session.commit()

    async def archive(self, *, idea: Idea, actor: CurrentUser, reason: str) -> Idea:
        if not await self.can_moderate(actor):
            raise PermissionDenied(permission=Permission.IDEA_MODERATE.value)
        if idea.status != "OPEN":
            raise Conflict("فقط ایدهٔ باز بایگانی می‌شود.")
        cleaned = reason.strip()
        if not cleaned:
            raise ValidationFailed("برای بایگانی ایده دلیل بنویس.")
        idea.status = "ARCHIVED"
        idea.archived_reason = cleaned
        await events.publish(self.session, events.IdeaWithdrawn(idea_id=idea.id))
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    # ── رأی — FR-IDEA-02 ───────────────────────────────────────────────
    async def vote(self, *, idea: Idea, actor: CurrentUser) -> Idea:
        if idea.author_id == actor.id:
            raise Conflict("به ایدهٔ خودت نمی‌توانی رأی بدهی.")
        if idea.status != "OPEN":
            raise Conflict("رأی‌گیری این ایده بسته است.")
        inserted = await self.session.scalar(
            insert(IdeaVote)
            .values(idea_id=idea.id, user_id=actor.id)
            .on_conflict_do_nothing()
            .returning(literal(1))
        )
        if inserted is None:
            raise DuplicateVote
        await self.session.flush()
        await self.session.refresh(idea)
        await events.publish(self.session, events.IdeaVoted(idea_id=idea.id))
        await self.session.commit()
        return idea

    async def unvote(self, *, idea: Idea, actor: CurrentUser) -> Idea:
        vote = await self.session.get(IdeaVote, (idea.id, actor.id))
        if vote is None:
            raise NotFound("رأیی برای پس گرفتن نیست.")
        await self.session.delete(vote)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    # ── نظر ────────────────────────────────────────────────────────────
    async def add_comment(
        self,
        *,
        idea: Idea,
        actor: CurrentUser,
        body: str,
        parent_id: uuid.UUID | None = None,
    ) -> IdeaComment:
        if idea.status == "ARCHIVED":
            raise Conflict("ایدهٔ بایگانی‌شده نظر نمی‌پذیرد.")
        cleaned = body.strip()
        if not 1 <= len(cleaned) <= COMMENT_MAX:
            raise ValidationFailed(f"نظر باید بین ۱ تا {COMMENT_MAX} نویسه باشد.")
        if parent_id is not None:
            parent = await self.session.get(IdeaComment, parent_id)
            if parent is None or parent.idea_id != idea.id or parent.deleted_at is not None:
                raise NotFound("نظری که به آن پاسخ می‌دهی پیدا نشد.")
            if parent.parent_id is not None:
                # نخ یک‌سطحی: پاسخ به پاسخ، پاسخ به همان ریشه است.
                parent_id = parent.parent_id
        comment = IdeaComment(
            idea_id=idea.id, author_id=actor.id, body=cleaned, parent_id=parent_id
        )
        self.session.add(comment)
        await self.session.flush()
        await events.publish(self.session, events.IdeaCommented(comment_id=comment.id))
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    async def delete_comment(self, *, comment_id: uuid.UUID, actor: CurrentUser) -> None:
        comment = await self.session.get(IdeaComment, comment_id)
        if comment is None or comment.deleted_at is not None:
            raise NotFound("نظر پیدا نشد.")
        if comment.author_id != actor.id and not await self.can_moderate(actor):
            raise PermissionDenied("فقط نویسندهٔ نظر یا ناظر می‌تواند آن را حذف کند.")
        comment.deleted_at = _now()
        await self.session.commit()

    # ── ارتقا — FR-IDEA-03، §7.8 ───────────────────────────────────────
    async def promote(
        self,
        *,
        idea: Idea,
        actor: CurrentUser,
        target: str,
        project_kind: str = "C_PROBLEM",
        expected_output: str | None = None,
    ) -> Promotion:
        if not await self.can_promote(actor):
            raise PermissionDenied(permission=Permission.IDEA_PROMOTE.value)
        # دو ارتقای هم‌زمان یک ایده، دو مقصد نمی‌سازند.
        locked = await self.session.scalar(select(Idea).where(Idea.id == idea.id).with_for_update())
        assert locked is not None
        await self.session.refresh(idea)
        if idea.status != "OPEN":
            raise Conflict("فقط ایدهٔ باز ارتقا می‌یابد.")

        if target == "PROJECT":
            target_id = await self._promote_to_project(
                idea, actor, kind=project_kind, expected_output=expected_output
            )
        elif target == "VENTURE":
            target_id = await self._promote_to_venture(idea)
        else:
            raise ValidationFailed("مقصد ارتقا باید پروژه یا کسب‌وکار باشد.")

        idea.status = "PROMOTED"
        idea.promoted_to_type = target
        idea.promoted_to_id = target_id
        idea.promoted_by = actor.id
        idea.promoted_at = _now()
        await events.publish(self.session, events.IdeaPromoted(idea_id=idea.id))
        if target == "VENTURE":
            await events.publish(self.session, events.VentureCreated(venture_id=target_id))
        await self.session.commit()
        await authz.invalidate_roles(actor.id)
        await authz.invalidate_roles(idea.author_id)
        log.info("idea_promoted", idea_id=str(idea.id), target=target, target_id=str(target_id))
        return Promotion(target_type=target, target_id=target_id)

    async def _promote_to_project(
        self, idea: Idea, actor: CurrentUser, *, kind: str, expected_output: str | None
    ) -> uuid.UUID:
        if kind not in PROJECT_KINDS:
            raise ValidationFailed("نوع پروژه معتبر نیست.")
        description = idea.body
        if idea.problem:
            description = f"{idea.body}\n\nمسئله: {idea.problem}"
        projects = ProjectService(self.session)
        project = await projects.build(
            lead_id=actor.id,
            draft=ProjectDraft(
                title_fa=idea.title,
                summary=_truncate(idea.problem or idea.body, SUMMARY_MAX),
                description=description,
                kind=kind,
                expected_output=(expected_output or "").strip() or "در گام نخست پروژه تعیین می‌شود.",
                tags=list(idea.tags),
                team_size_max=5,
                work_style="TEAM",
            ),
            origin_idea_id=idea.id,
        )
        team = await projects.ensure_team(project)
        if idea.author_id != actor.id:
            await InvitationService(self.session).invite(
                team=team,
                inviter_id=actor.id,
                invitee_id=idea.author_id,
                source="IDEA_PROMOTION",
                message="این پروژه از ایدهٔ تو ساخته شد. به تیمش بپیوند.",
                commit=False,
            )
        return project.id

    async def _promote_to_venture(self, idea: Idea) -> uuid.UUID:
        if idea.is_anonymous:
            raise Conflict(
                "ایدهٔ ناشناس به کسب‌وکار ارتقا نمی‌یابد، چون صفحهٔ کسب‌وکار بنیان‌گذار"
                " را نشان می‌دهد. نویسنده می‌تواند نامش را آشکار کند، یا ایده به پروژه"
                " ارتقا یابد."
            )
        venture = await VentureService(self.session).build(
            founder_id=idea.author_id,
            draft=VentureDraft(
                name=_truncate(idea.title, 120),
                pitch=_truncate(idea.body, SUMMARY_MAX),
                description=idea.body,
                problem=idea.problem,
            ),
            origin_idea_id=idea.id,
        )
        return venture.id

    # ── درونی ──────────────────────────────────────────────────────────
    def _apply(self, idea: Idea, draft: IdeaDraft) -> None:
        title = " ".join(draft.title.split())
        body = draft.body.strip()
        problem = (draft.problem or "").strip() or None
        if not 3 <= len(title) <= TITLE_MAX:
            raise ValidationFailed(f"عنوان ایده باید بین ۳ تا {TITLE_MAX} نویسه باشد.")
        if not 10 <= len(body) <= BODY_MAX:
            raise ValidationFailed(f"شرح ایده باید بین ۱۰ تا {BODY_MAX} نویسه باشد.")
        if problem is not None and len(problem) > PROBLEM_MAX:
            raise ValidationFailed(f"شرح مسئله حداکثر {PROBLEM_MAX} نویسه است.")
        if draft.category is not None and draft.category not in IDEA_CATEGORIES:
            raise ValidationFailed("دستهٔ ایده معتبر نیست.")
        try:
            tags = rules.clean_tags(draft.tags)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        idea.title = title
        idea.body = body
        idea.problem = problem
        idea.category = draft.category
        idea.tags = tags
        idea.is_anonymous = draft.is_anonymous


__all__ = ["IDEA_SORTS", "IdeaDraft", "IdeaService", "Promotion", "hot_score_sql"]
