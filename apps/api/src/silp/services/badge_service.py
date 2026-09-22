"""نشان‌ها — PRD §9.5، FR-GAM-03، M5-05.

«**ارزیابی:** کار پس‌زمینهٔ `evaluate_badges` هر ۱۰ دقیقه، برای کاربرانی که
از آخرین ارزیابی امتیاز گرفته‌اند، معیارها را بررسی می‌کند. **نه در مسیر
درخواست** — تا تأخیر ایجاد نکند.»

«از آخرین ارزیابی» با یک پنجرهٔ نگاه‌به‌عقب پیاده شده، نه با مکان‌نمای
ذخیره‌شده. مکان‌نما روی `created_at` امن نیست: `now()` زمان **شروع**
تراکنش است، پس ردیفی که دیرتر commit شد می‌تواند زمانی پیش از مکان‌نمای
قبلی داشته باشد و برای همیشه جا بماند. پنجره بزرگ‌تر از فاصلهٔ اجراست و
ارزیابی بی‌اثر در تکرار است (کلید اصلی `user_badges`)، پس هم‌پوشانی هزینه
دارد ولی خطا ندارد. اجرای شبانه‌ای با `all_users=True` جاماندهٔ زمان خرابی
کارگر را هم می‌گیرد.

## واقعیت‌ها از کجا می‌آیند

| واقعیت | منبع |
|--------|------|
| شمارش قواعد (`QUIZ_PERFECT`، …) | ردیف‌های **فعال** دفتر کل — معکوس‌شده شمرده نمی‌شود |
| `PROJECT_COMPLETED` به تفکیک نوع | همان، پیوند به `projects.kind` |
| `WEEKLY_ACTIVITY`، `NIGHT_ACTIVITY` | زمان ردیف‌های فعال، به وقت تهران |
| `DELIVERABLE_APPROVED` | `deliverables` — مستقل از اینکه امتیاز مرحله به چه کسی رسید |
| `TEAM_JOINED` | `team_members` — ترک‌کرده هم عضو بوده، اخراج‌شده نه |
| `APPLICATION_SUBMITTED` | فاصلهٔ ثبت‌نام تا اولین درخواست پروژه |

واقعیت‌های ماژول‌های M7 (فروش، مقالهٔ Q1، شهر هوشمند) هنوز منبعی ندارند و
صفرند؛ نشانشان قفل می‌ماند و بقیه ارزیابی می‌شوند.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from silp.core.logging import get_logger
from silp.domain.gamification import formulas
from silp.domain.gamification.badges import (
    BadgeFacts,
    InvalidCriteria,
    Progress,
    count_key,
    evaluate,
    longest_weekly_streak,
)
from silp.models.delivery import Deliverable
from silp.models.gamification import POINT_CATEGORIES, Badge, PointEntry, UserBadge
from silp.models.identity import User
from silp.models.project import Project, ProjectApplication, TeamMember

log = get_logger("silp.badges")

#: پنجرهٔ نگاه‌به‌عقب — چند برابر فاصلهٔ ۱۰ دقیقه‌ای اجرا.
DEFAULT_LOOKBACK = timedelta(hours=2)


@dataclass(frozen=True, slots=True)
class BadgeStatus:
    badge: Badge
    awarded_at: datetime | None
    seen_at: datetime | None
    progress: Progress

    @property
    def earned(self) -> bool:
        return self.awarded_at is not None


def _now() -> datetime:
    return datetime.now(UTC)


def _active_originals() -> Any:
    """ردیف‌های اصلیِ معکوس‌نشده — «چیزی که هنوز به حساب می‌آید»."""
    reversal = aliased(PointEntry)
    return (
        PointEntry.reverses_id.is_(None),
        ~exists().where(reversal.reverses_id == PointEntry.id),
    )


class BadgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── واقعیت‌ها ──────────────────────────────────────────────────────
    async def facts_for(self, user_id: uuid.UUID) -> BadgeFacts:
        points = {c: Decimal(0) for c in POINT_CATEGORIES}
        for category, total in await self.session.execute(
            select(PointEntry.category, func.sum(PointEntry.amount))
            .where(PointEntry.user_id == user_id)
            .group_by(PointEntry.category)
        ):
            points[category] = total or Decimal(0)

        originals = list(
            await self.session.execute(
                select(PointEntry.rule_code, PointEntry.source_id, PointEntry.created_at).where(
                    PointEntry.user_id == user_id, *_active_originals()
                )
            )
        )
        counts: Counter[str] = Counter()
        for rule_code, _, _ in originals:
            counts[rule_code] += 1

        completed_projects = [sid for rule, sid, _ in originals if rule == "PROJECT_COMPLETED"]
        if completed_projects:
            for kind, n in await self.session.execute(
                select(Project.kind, func.count())
                .where(Project.id.in_(completed_projects))
                .group_by(Project.kind)
            ):
                counts[count_key("PROJECT_COMPLETED", kind)] = n

        counts["NIGHT_ACTIVITY"] = sum(1 for _, _, at in originals if formulas.is_night(at))
        counts["DELIVERABLE_APPROVED"] = (
            await self.session.scalar(
                select(func.count())
                .select_from(Deliverable)
                .where(Deliverable.submitter_id == user_id, Deliverable.status == "APPROVED")
            )
            or 0
        )
        counts["TEAM_JOINED"] = (
            await self.session.scalar(
                select(func.count(func.distinct(TeamMember.team_id))).where(
                    TeamMember.user_id == user_id, TeamMember.status.in_(("ACTIVE", "LEFT"))
                )
            )
            or 0
        )

        days_to_first: dict[str, int] = {}
        row = (
            await self.session.execute(
                select(User.created_at, func.min(ProjectApplication.created_at))
                .outerjoin(ProjectApplication, ProjectApplication.applicant_id == User.id)
                .where(User.id == user_id)
                .group_by(User.created_at)
            )
        ).first()
        if row is not None and row[1] is not None:
            days_to_first["APPLICATION_SUBMITTED"] = max((row[1] - row[0]).days, 0)

        return BadgeFacts(
            points_by_category=points,
            counts=dict(counts),
            streaks={
                "WEEKLY_ACTIVITY": longest_weekly_streak(
                    formulas.week_key(at) for _, _, at in originals
                )
            },
            days_to_first=days_to_first,
        )

    # ── ارزیابی ────────────────────────────────────────────────────────
    async def evaluate_user(self, user_id: uuid.UUID) -> list[str]:
        """نشان‌های تازه‌کسب‌شدهٔ این کاربر را اعطا می‌کند. خروجی: کدهای تازه."""
        earned = set(
            await self.session.scalars(
                select(UserBadge.badge_code).where(UserBadge.user_id == user_id)
            )
        )
        candidates = [b for b in await self._active_badges() if b.code not in earned]
        if not candidates:
            return []

        facts = await self.facts_for(user_id)
        awarded: list[str] = []
        for badge in candidates:
            try:
                result = evaluate(badge.criteria, facts)
            except InvalidCriteria:
                # معیار خراب یک نشان، ارزیابی بقیه را متوقف نمی‌کند.
                log.warning("badge_criteria_invalid", badge=badge.code)
                continue
            if not result.met:
                continue
            inserted = await self.session.scalar(
                insert(UserBadge)
                .values(
                    user_id=user_id,
                    badge_code=badge.code,
                    context={"current": str(result.current), "target": str(result.target)},
                )
                .on_conflict_do_nothing(index_elements=["user_id", "badge_code"])
                .returning(UserBadge.badge_code)
            )
            if inserted is not None:
                awarded.append(inserted)
        if awarded:
            log.info("badges_awarded", user_id=str(user_id), badges=awarded)
        return awarded

    async def evaluate_recent(
        self, *, lookback: timedelta = DEFAULT_LOOKBACK, all_users: bool = False
    ) -> int:
        """کار `evaluate_badges` — §9.5. خروجی: تعداد نشان‌های اعطاشده."""
        since = _now() - lookback
        if all_users:
            users = set(await self.session.scalars(select(PointEntry.user_id).distinct()))
            users |= set(
                await self.session.scalars(select(ProjectApplication.applicant_id).distinct())
            )
        else:
            users = set(
                await self.session.scalars(
                    select(PointEntry.user_id).where(PointEntry.created_at >= since).distinct()
                )
            )
            # «شروع سریع» با درخواست کسب می‌شود و درخواست امتیازی نمی‌دهد.
            users |= set(
                await self.session.scalars(
                    select(ProjectApplication.applicant_id)
                    .where(ProjectApplication.created_at >= since)
                    .distinct()
                )
            )
        total = 0
        for user_id in sorted(users):
            total += len(await self.evaluate_user(user_id))
        await self.session.commit()
        return total

    # ── خواندن ─────────────────────────────────────────────────────────
    async def statuses(self, user_id: uuid.UUID) -> list[BadgeStatus]:
        """همهٔ نشان‌ها با وضعیت کاربر — کسب‌شده‌ها و قفل‌ها با پیشرفت."""
        earned = {
            row.badge_code: row
            for row in await self.session.scalars(
                select(UserBadge).where(UserBadge.user_id == user_id)
            )
        }
        facts = await self.facts_for(user_id)
        result: list[BadgeStatus] = []
        for badge in await self._active_badges():
            own = earned.get(badge.code)
            try:
                progress = evaluate(badge.criteria, facts)
            except InvalidCriteria:
                progress = Progress(met=False, current=Decimal(0), target=Decimal(1))
            if own is not None:
                progress = Progress(met=True, current=progress.target, target=progress.target)
            result.append(
                BadgeStatus(
                    badge=badge,
                    awarded_at=own.awarded_at if own else None,
                    seen_at=own.seen_at if own else None,
                    progress=progress,
                )
            )
        return result

    async def recent(self, user_id: uuid.UUID, *, limit: int = 3) -> list[tuple[Badge, UserBadge]]:
        rows = await self.session.execute(
            select(Badge, UserBadge)
            .join(UserBadge, UserBadge.badge_code == Badge.code)
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.awarded_at.desc())
            .limit(limit)
        )
        return list(rows.tuples())

    async def mark_seen(self, user_id: uuid.UUID, codes: list[str] | None = None) -> int:
        """جشن دیده شد — مودال دوباره باز نمی‌شود (§9.10)."""
        statement = (
            update(UserBadge)
            .where(UserBadge.user_id == user_id, UserBadge.seen_at.is_(None))
            .values(seen_at=_now())
        )
        if codes:
            statement = statement.where(UserBadge.badge_code.in_(codes))
        result = await self.session.execute(statement)
        await self.session.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def _active_badges(self) -> list[Badge]:
        rows = await self.session.scalars(
            select(Badge).where(Badge.is_active.is_(True)).order_by(Badge.sort_order, Badge.code)
        )
        return list(rows)


__all__ = ["DEFAULT_LOOKBACK", "BadgeService", "BadgeStatus"]
