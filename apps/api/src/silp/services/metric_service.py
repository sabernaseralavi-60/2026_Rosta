"""شاخص‌های فعالیت و فروش — FR-VEN-02، M7-04.

یک ردیف شاخص مال **یک** کسب‌وکار یا **یک** پروژهٔ عملیاتی (نوع A) است،
و سه مرحله دارد: عضو ثبت می‌کند، کس دیگری تأیید یا رد می‌کند، و تأیید
امتیاز `STARTUP` می‌دهد (شنونده در `point_listeners`).

## چه کسی تأیید می‌کند

| شاخص | تأییدکننده |
|------|------------|
| کسب‌وکار | `venture.metric.verify` — منتور، استاد، مدیر آموزشی، مدیر |
| پروژه | `project.metric.verify` در قلمرو پروژه — مدیر پروژه، منتور، استاد |

و در هر دو حالت **نه خودِ ثبت‌کننده** — قید `not_self_reviewed` در
دیتابیس هم همین را می‌پاید.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    NotFound,
    NotTeamMember,
    PermissionDenied,
    UploadIncomplete,
    ValidationFailed,
)
from silp.core.permissions import CurrentUser, Permission
from silp.domain.calendar import MONTHS_FA, to_jalali
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.text import to_persian_digits
from silp.domain.ventures import share_of, share_percent_of
from silp.models.file import File
from silp.models.project import Project
from silp.models.venture import METRIC_KINDS, NOTE_MAX, Venture, VentureMetric
from silp.services import authz, events
from silp.services.project_service import ProjectService
from silp.services.venture_service import VentureService

#: ثبت عقب‌افتاده تا شش ماه پذیرفته است؛ دورتر از آن قابل راستی‌آزمایی نیست.
BACKDATE_LIMIT = timedelta(days=180)
MAX_COUNT_VALUE = 10_000
#: هزار میلیارد ریال — بزرگ‌تر از این غلط تایپی است، نه فروش دانشجویی.
MAX_SALES_RIAL = 1_000_000_000_000
REVIEW_DECISIONS = ("VERIFIED", "REJECTED")
ACTIVE_PROJECT_STATUSES = ("OPEN", "IN_PROGRESS")
QUEUE_LIMIT = 200
#: گزارش درآمد شخصی — سقف امن؛ یک دانشجو در یک ترم به صدها فروش نمی‌رسد.
REVENUE_ROW_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class MetricOwner:
    venture: Venture | None = None
    project: Project | None = None

    @property
    def title(self) -> str:
        if self.venture is not None:
            return self.venture.name
        assert self.project is not None
        return self.project.title_fa


@dataclass(slots=True)
class MetricTotals:
    """جمع هر شاخص — تأییدشده و در انتظار جدا (FR-VEN-02 «داشبورد عملکرد»)."""

    verified: dict[str, int] = field(default_factory=dict)
    pending: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RevenueLine:
    """یک فروش تأییدشدهٔ پروژه و سهمی که هنگام تأیید از آن ثبت شد."""

    metric_id: uuid.UUID
    project_id: uuid.UUID
    project_title: str
    occurred_on: date
    value: int
    share_percent: Decimal
    share_rial: int
    note: str | None


@dataclass(slots=True)
class RevenueMonth:
    year: int
    month: int
    sales_rial: int = 0
    share_rial: int = 0
    lines: list[RevenueLine] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{MONTHS_FA[self.month - 1]} {to_persian_digits(self.year)}"


@dataclass(slots=True)
class RevenueReport:
    """گزارش درآمد شخصی — FR-VEN-03. فقط ثبت و گزارش؛ پرداخت بیرون از سامانه است."""

    months: list[RevenueMonth] = field(default_factory=list)
    total_sales_rial: int = 0
    total_share_rial: int = 0
    #: ثبت‌شده و هنوز بی‌بررسی — سهمش وقتی روشن می‌شود که تأیید شود.
    pending_sales_rial: int = 0
    pending_count: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().astimezone(LOCAL_TZ).date()


class MetricService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ventures = VentureService(session)
        self.projects = ProjectService(session)

    # ── ثبت ────────────────────────────────────────────────────────────
    async def record(
        self,
        *,
        owner: MetricOwner,
        actor: CurrentUser,
        metric: str,
        value: int,
        occurred_on: date,
        note: str | None = None,
        evidence_file_id: uuid.UUID | None = None,
    ) -> VentureMetric:
        await self._require_recorder(owner, actor)
        if metric not in METRIC_KINDS:
            raise ValidationFailed("نوع شاخص معتبر نیست.")
        limit = MAX_SALES_RIAL if metric == "SALES_AMOUNT" else MAX_COUNT_VALUE
        if not 0 < value <= limit:
            raise ValidationFailed("مقدار شاخص باید عددی مثبت و واقع‌بینانه باشد.")
        today = _today()
        if occurred_on > today:
            raise ValidationFailed("تاریخ فعالیت نمی‌تواند در آینده باشد.")
        if occurred_on < today - BACKDATE_LIMIT:
            raise ValidationFailed("فعالیت‌های بیش از شش ماه پیش ثبت نمی‌شوند.")
        cleaned_note = (note or "").strip() or None
        if cleaned_note is not None and len(cleaned_note) > NOTE_MAX:
            raise ValidationFailed(f"توضیح حداکثر {NOTE_MAX} نویسه است.")
        if evidence_file_id is not None:
            await self._require_evidence(evidence_file_id, actor.id)

        row = VentureMetric(
            venture_id=owner.venture.id if owner.venture else None,
            project_id=owner.project.id if owner.project else None,
            user_id=actor.id,
            metric=metric,
            value=value,
            occurred_on=occurred_on,
            note=cleaned_note,
            evidence_file_id=evidence_file_id,
            status="PENDING",
        )
        self.session.add(row)
        if owner.project is not None:
            await self.projects.record_activity(
                owner.project,
                actor.id,
                "METRIC_RECORDED",
                "یک فعالیت یا فروش تازه ثبت شد.",
                entity_type="metric",
                commit=False,
            )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, *, metric_id: uuid.UUID, actor: CurrentUser) -> None:
        row = await self.require(metric_id)
        if row.user_id != actor.id:
            raise PermissionDenied("فقط ثبت‌کننده می‌تواند این ردیف را حذف کند.")
        if row.status != "PENDING":
            raise Conflict("ردیفی که بررسی شده حذف نمی‌شود.")
        await self.session.delete(row)
        await self.session.commit()

    # ── خواندن ─────────────────────────────────────────────────────────
    async def require(self, metric_id: uuid.UUID) -> VentureMetric:
        row = await self.session.get(VentureMetric, metric_id)
        if row is None:
            raise NotFound("این ردیف پیدا نشد.")
        return row

    async def owner_of(self, row: VentureMetric) -> MetricOwner:
        if row.venture_id is not None:
            return MetricOwner(venture=await self.ventures.require(row.venture_id))
        assert row.project_id is not None
        return MetricOwner(project=await self.projects.require(row.project_id))

    async def list_for(
        self, owner: MetricOwner, *, status: str | None = None, limit: int = 200
    ) -> list[VentureMetric]:
        stmt = select(VentureMetric).where(self._owner_clause(owner))
        if status:
            stmt = stmt.where(VentureMetric.status == status)
        rows = await self.session.scalars(
            stmt.order_by(VentureMetric.occurred_on.desc(), VentureMetric.created_at.desc()).limit(
                limit
            )
        )
        return list(rows)

    async def totals(
        self, owner: MetricOwner
    ) -> tuple[MetricTotals, dict[uuid.UUID, MetricTotals]]:
        """جمع کل و جمع هر عضو — یک کوئری، گروه‌بندی در SQL."""
        rows = await self.session.execute(
            select(
                VentureMetric.user_id,
                VentureMetric.metric,
                VentureMetric.status,
                func.sum(VentureMetric.value),
            )
            .where(self._owner_clause(owner), VentureMetric.status != "REJECTED")
            .group_by(VentureMetric.user_id, VentureMetric.metric, VentureMetric.status)
        )
        overall = MetricTotals()
        by_member: dict[uuid.UUID, MetricTotals] = defaultdict(MetricTotals)
        for user_id, metric, status, total in rows:
            bucket = "verified" if status == "VERIFIED" else "pending"
            amount = int(total or 0)
            for target in (overall, by_member[user_id]):
                values = getattr(target, bucket)
                values[metric] = values.get(metric, 0) + amount
        return overall, dict(by_member)

    async def member_shares(self, project: Project) -> dict[uuid.UUID, int]:
        """جمع سهم تأییدشدهٔ هر عضو در یک پروژه (ADR-0025 بند ۶)."""
        rows = await self.session.execute(
            select(VentureMetric.user_id, func.sum(VentureMetric.share_rial))
            .where(
                VentureMetric.project_id == project.id,
                VentureMetric.status == "VERIFIED",
                VentureMetric.share_rial.is_not(None),
            )
            .group_by(VentureMetric.user_id)
        )
        return {user_id: int(total or 0) for user_id, total in rows}

    async def revenue_report(self, user_id: uuid.UUID) -> RevenueReport:
        """فروش‌های پروژه‌ای یک فروشنده به تفکیک ماه شمسی (روز فروش، نه روز تأیید)."""
        rows = await self.session.execute(
            select(VentureMetric, Project.title_fa)
            .join(Project, Project.id == VentureMetric.project_id)
            .where(
                VentureMetric.user_id == user_id,
                VentureMetric.metric == "SALES_AMOUNT",
                VentureMetric.status.in_(("VERIFIED", "PENDING")),
            )
            .order_by(VentureMetric.occurred_on.desc(), VentureMetric.created_at.desc())
            .limit(REVENUE_ROW_LIMIT)
        )
        report = RevenueReport()
        by_month: dict[tuple[int, int], RevenueMonth] = {}
        for row, title in rows:
            if row.status == "PENDING":
                report.pending_sales_rial += row.value
                report.pending_count += 1
                continue
            assert row.project_id is not None
            year, month, _ = to_jalali(row.occurred_on)
            bucket = by_month.setdefault((year, month), RevenueMonth(year=year, month=month))
            share = row.share_rial or 0
            bucket.sales_rial += row.value
            bucket.share_rial += share
            bucket.lines.append(
                RevenueLine(
                    metric_id=row.id,
                    project_id=row.project_id,
                    project_title=title,
                    occurred_on=row.occurred_on,
                    value=row.value,
                    share_percent=row.share_percent or Decimal(0),
                    share_rial=share,
                    note=row.note,
                )
            )
            report.total_sales_rial += row.value
            report.total_share_rial += share
        report.months = [by_month[key] for key in sorted(by_month, reverse=True)]
        return report

    async def can_view(self, owner: MetricOwner, actor: CurrentUser) -> bool:
        if owner.venture is not None:
            return await self.ventures.is_member(
                owner.venture.id, actor.id
            ) or await authz.has_permission(self.session, actor, Permission.VENTURE_METRIC_VERIFY)
        assert owner.project is not None
        if await self.projects.membership(owner.project.id, actor.id) is not None:
            return True
        return await authz.has_permission(
            self.session, actor, Permission.PROJECT_METRIC_VERIFY, owner.project.id
        ) or await authz.has_permission(
            self.session, actor, Permission.PROJECT_WORKSPACE_VIEW, owner.project.id
        )

    async def can_review(self, row: VentureMetric, actor: CurrentUser) -> bool:
        if row.user_id == actor.id:
            return False
        if row.venture_id is not None:
            return await authz.has_permission(self.session, actor, Permission.VENTURE_METRIC_VERIFY)
        return await authz.has_permission(
            self.session, actor, Permission.PROJECT_METRIC_VERIFY, row.project_id
        )

    async def review_queue(self, actor: CurrentUser) -> list[VentureMetric]:
        """شاخص‌های در انتظاری که این کاربر حق تأییدشان را دارد — قدیمی‌ترین اول."""
        rows = list(
            await self.session.scalars(
                select(VentureMetric)
                .where(VentureMetric.status == "PENDING", VentureMetric.user_id != actor.id)
                .order_by(VentureMetric.created_at)
                .limit(QUEUE_LIMIT)
            )
        )
        may_verify_ventures = await authz.has_permission(
            self.session, actor, Permission.VENTURE_METRIC_VERIFY
        )
        allowed_projects: dict[uuid.UUID, bool] = {}
        result: list[VentureMetric] = []
        for row in rows:
            if row.venture_id is not None:
                if may_verify_ventures:
                    result.append(row)
                continue
            assert row.project_id is not None
            if row.project_id not in allowed_projects:
                allowed_projects[row.project_id] = await authz.has_permission(
                    self.session, actor, Permission.PROJECT_METRIC_VERIFY, row.project_id
                )
            if allowed_projects[row.project_id]:
                result.append(row)
        return result

    # ── بررسی ──────────────────────────────────────────────────────────
    async def review(
        self,
        *,
        metric_id: uuid.UUID,
        actor: CurrentUser,
        decision: str,
        note: str | None = None,
    ) -> VentureMetric:
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        row = await self.session.scalar(
            select(VentureMetric).where(VentureMetric.id == metric_id).with_for_update()
        )
        if row is None:
            raise NotFound("این ردیف پیدا نشد.")
        if row.user_id == actor.id:
            raise PermissionDenied("ثبت خودت را نمی‌توانی تأیید کنی.")
        if not await self.can_review(row, actor):
            raise PermissionDenied(
                "تأیید این شاخص با منتور، استاد یا مدیر پروژه است.",
                permission=(
                    Permission.VENTURE_METRIC_VERIFY
                    if row.venture_id
                    else Permission.PROJECT_METRIC_VERIFY
                ).value,
            )
        if row.status != "PENDING":
            raise Conflict("این ردیف قبلاً بررسی شده است.")
        cleaned = (note or "").strip() or None
        if decision == "REJECTED" and cleaned is None:
            raise ValidationFailed("برای رد کردن، دلیل بنویس تا ثبت‌کننده بداند چه کند.")
        row.status = decision
        row.reviewed_by = actor.id
        row.reviewed_at = _now()
        row.review_note = cleaned
        if decision == "VERIFIED":
            await self._snapshot_share(row)
        await events.publish(self.session, events.MetricReviewed(metric_id=row.id))
        await self.session.commit()
        await self.session.refresh(row)
        return row

    # ── درونی ──────────────────────────────────────────────────────────
    async def _snapshot_share(self, row: VentureMetric) -> None:
        """سهم فروشنده را هنگام تأیید ثابت می‌کند (ADR-0025 بند ۳).

        فقط فروش پروژه؛ فروش کسب‌وکار توافق درصدی ندارد.
        """
        if row.metric != "SALES_AMOUNT" or row.project_id is None:
            return
        project = await self.session.get(Project, row.project_id)
        percent = share_percent_of(project.rewards if project else None)
        row.share_percent = percent
        row.share_rial = share_of(row.value, percent)

    @staticmethod
    def _owner_clause(owner: MetricOwner):  # type: ignore[no-untyped-def]
        if owner.venture is not None:
            return VentureMetric.venture_id == owner.venture.id
        assert owner.project is not None
        return VentureMetric.project_id == owner.project.id

    async def _require_recorder(self, owner: MetricOwner, actor: CurrentUser) -> None:
        if owner.venture is not None:
            if owner.venture.stage == "CLOSED":
                raise Conflict("این کسب‌وکار بسته شده است.")
            await self.ventures.require_member(owner.venture, actor)
            return
        project = owner.project
        assert project is not None
        if project.kind != "A_VENTURE":
            raise Conflict("ثبت فعالیت و فروش فقط برای پروژه‌های کارآفرینی است.")
        if project.status not in ACTIVE_PROJECT_STATUSES:
            raise Conflict("این پروژه فعال نیست.")
        if await self.projects.membership(project.id, actor.id) is None:
            raise NotTeamMember

    async def _require_evidence(self, file_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        file = await self.session.get(File, file_id)
        if file is None or file.uploaded_by != owner_id or file.deleted_at is not None:
            raise NotFound("فایل مستند پیدا نشد.")
        if not file.is_attachable:
            raise UploadIncomplete


__all__ = [
    "MetricOwner",
    "MetricService",
    "MetricTotals",
    "RevenueLine",
    "RevenueMonth",
    "RevenueReport",
]
