"""ارزیابی همتا — FR-PRJ-08، ADR-0024 برش ب.

یک فراخوانی برای **همهٔ** هم‌تیمی‌ها، یک‌بار و بی‌ویرایش. امتیاز برای *انجام*
است نه برای *مقدار* (۵ ستاره دادن به همه چیزی نمی‌خرد). نتیجه فقط تجمیعی
و فقط برای مدیر پروژه است؛ ارزیابی‌شونده و استاد آن را نمی‌بینند.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotTeamMember, PermissionDenied, ValidationFailed
from silp.core.permissions import CurrentUser
from silp.domain import peer_evaluations as rules
from silp.domain.peer_evaluations import PeerRating
from silp.models.delivery import PeerEvaluation
from silp.models.project import Project, Team, TeamMember
from silp.services import events
from silp.services.directory import display_names, name_of
from silp.services.points_service import PointsService
from silp.services.project_service import ProjectService

RULE_CODE = "PEER_EVAL_COMPLETED"


@dataclass(frozen=True, slots=True)
class Peer:
    user_id: uuid.UUID
    full_name: str | None
    is_lead: bool


@dataclass(frozen=True, slots=True)
class PeerEvaluationState:
    """آنچه فرم برای نشان دادن خودش لازم دارد — یک فراخوانی، نه سه‌تا."""

    can_submit: bool
    reason: str | None
    peers: list[Peer]
    #: ارزیابی‌های ثبت‌شدهٔ خودِ کاربر (فقط‌خواندنی)؛ خالی تا وقتی ثبت نکرده.
    mine: list[PeerEvaluation]
    points: Decimal | None


@dataclass(frozen=True, slots=True)
class PeerAverage:
    user_id: uuid.UUID
    full_name: str | None
    evaluations: int
    contribution_avg: float | None
    reliability_avg: float | None


class PeerEvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    async def state(self, *, project: Project, actor: CurrentUser) -> PeerEvaluationState:
        """وضعیت ارزیابی خودِ کاربر. غیرعضو ۴۰۳ می‌گیرد (مثل بقیهٔ فضای کاری)."""
        await self._require_member(project, actor)
        peers = await self._peers(project.id, actor.id)
        mine = await self._mine(project.id, actor.id)
        points = await self._reward()
        if mine:
            return PeerEvaluationState(
                False, "ارزیابی این پروژه را ثبت کرده‌ای.", peers, mine, points
            )
        if project.status != "COMPLETED":
            reason = "ارزیابی همتا پس از بسته شدن پروژه انجام می‌شود."
            return PeerEvaluationState(False, reason, peers, [], points)
        if not peers:
            reason = "تیم تک‌نفره همتایی برای ارزیابی ندارد."
            return PeerEvaluationState(False, reason, peers, [], points)
        return PeerEvaluationState(True, None, peers, [], points)

    async def submit(
        self, *, project: Project, actor: CurrentUser, ratings: list[PeerRating]
    ) -> PeerEvaluationState:
        await self._require_member(project, actor)
        if project.status != "COMPLETED":
            raise Conflict("ارزیابی همتا پس از بسته شدن پروژه انجام می‌شود.")
        peers = await self._peers(project.id, actor.id)
        if not peers:
            raise Conflict("تیم تک‌نفره همتایی برای ارزیابی ندارد.")
        problem = rules.validate(ratings, [peer.user_id for peer in peers])
        if problem is not None:
            raise ValidationFailed(problem)
        if await self._mine(project.id, actor.id):
            raise Conflict("ارزیابی این پروژه را قبلاً ثبت کرده‌ای.")

        try:
            async with self.session.begin_nested():
                for rating in ratings:
                    self.session.add(
                        PeerEvaluation(
                            project_id=project.id,
                            evaluator_id=actor.id,
                            evaluatee_id=rating.evaluatee_id,
                            contribution=rating.contribution,
                            reliability=rating.reliability,
                        )
                    )
                await self.session.flush()
        except IntegrityError:
            # دو کلیک هم‌زمان: کلید اصلی دومی را رد می‌کند.
            raise Conflict("ارزیابی این پروژه را قبلاً ثبت کرده‌ای.") from None
        await events.publish(
            self.session,
            events.PeerEvaluationsSubmitted(project_id=project.id, evaluator_id=actor.id),
        )
        await self.session.commit()
        return await self.state(project=project, actor=actor)

    async def summary(self, *, project: Project, actor: CurrentUser) -> list[PeerAverage]:
        """میانگین دریافتیِ هر عضو، فقط برای مدیر پروژه — FR-PRJ-08.

        دو تصمیم برای حفظ ناشناسی:

        * ردیف خودِ مدیر نیست (ارزیابی‌شونده نتیجهٔ خودش را نمی‌بیند).
        * ارزیابی خودِ مدیر در میانگینِ دیگران **نمی‌آید**: او نظر خودش را
          می‌داند و در تیم سه‌نفره با کم‌کردنش نظر نفر سوم را عیناً می‌فهمید.
          آستانهٔ کمینه هم روی همین ارزیابی‌های «دیگران» سنجیده می‌شود.
        """
        membership = await self.projects.membership(project.id, actor.id)
        if membership is None:
            raise NotTeamMember
        if not membership.is_lead:
            raise PermissionDenied("نتیجهٔ ارزیابی همتا فقط برای مدیر پروژه است.")

        peers = await self._peers(project.id, actor.id)
        rows = await self.session.execute(
            select(
                PeerEvaluation.evaluatee_id,
                PeerEvaluation.contribution,
                PeerEvaluation.reliability,
            ).where(
                PeerEvaluation.project_id == project.id,
                PeerEvaluation.evaluator_id != actor.id,
            )
        )
        contribution: dict[uuid.UUID, list[int]] = defaultdict(list)
        reliability: dict[uuid.UUID, list[int]] = defaultdict(list)
        for evaluatee_id, given, dependable in rows:
            contribution[evaluatee_id].append(given)
            if dependable is not None:
                reliability[evaluatee_id].append(dependable)

        return [
            PeerAverage(
                user_id=peer.user_id,
                full_name=peer.full_name,
                evaluations=len(contribution[peer.user_id]),
                contribution_avg=rules.average(contribution[peer.user_id]),
                reliability_avg=rules.average(reliability[peer.user_id]),
            )
            for peer in peers
        ]

    # ── درونی ──────────────────────────────────────────────────────────
    async def _require_member(self, project: Project, actor: CurrentUser) -> None:
        if await self.projects.membership(project.id, actor.id) is None:
            raise NotTeamMember

    async def _peers(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Peer]:
        """اعضای فعالِ دیگر، مدیر پیش از بقیه."""
        rows = await self.session.execute(
            select(TeamMember.user_id, TeamMember.is_lead)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.project_id == project_id,
                TeamMember.status == "ACTIVE",
                TeamMember.user_id != user_id,
            )
            .order_by(TeamMember.is_lead.desc(), TeamMember.joined_at)
        )
        members = list(rows.tuples().all())
        names = await display_names(self.session, [member_id for member_id, _ in members])
        return [Peer(member_id, name_of(names, member_id), lead) for member_id, lead in members]

    async def _mine(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[PeerEvaluation]:
        rows = await self.session.scalars(
            select(PeerEvaluation)
            .where(PeerEvaluation.project_id == project_id, PeerEvaluation.evaluator_id == user_id)
            .order_by(PeerEvaluation.created_at, PeerEvaluation.evaluatee_id)
        )
        return list(rows)

    async def _reward(self) -> Decimal | None:
        """امتیاز فعلی قاعده — مدیر آن را عوض می‌کند، پس ثابت در کد نمی‌گذاریم."""
        rule = await PointsService(self.session).rule(RULE_CODE)
        return rule.base_points if rule is not None and rule.is_active else None


__all__ = [
    "RULE_CODE",
    "Peer",
    "PeerAverage",
    "PeerEvaluationService",
    "PeerEvaluationState",
]
