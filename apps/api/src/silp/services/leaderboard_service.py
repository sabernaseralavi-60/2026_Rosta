"""جدول رتبه‌بندی — PRD §9.7، FR-GAM-04، M5-07.

قواعد انصاف §9.7، هر پنج تا اینجا اعمال می‌شوند:

۱. **همیشه محدود به نیم‌سال.** رتبه‌بندی مادام‌العمر تازه‌وارد را ناامید
   می‌کند. سطحِ کنار نام مادام‌العمر است، رتبه نه.
۲. **فقط ۱۰ نفر برتر** + رتبه و صدک خود کاربر.
۳. **هیچ‌کس رتبهٔ پایین جدول را نمی‌بیند** — پاسخ جز ۱۰ نفر برتر و خودت،
   هیچ ردیفی ندارد؛ حتی شمار کل شرکت‌کنندگان هم برای دیگران برنمی‌گردد.
۴. **انصراف آزاد** — `profiles.show_in_leaderboard = false` کاربر را از
   جدول دیگران حذف می‌کند، ولی خودش رتبه‌اش را می‌بیند. رتبه در میان
   «کسانی که در جدول‌اند، به‌علاوهٔ خودت» حساب می‌شود؛ وگرنه کسی که
   منصرف شده، از جدول غایب است ولی جای رتبهٔ اول را خالی نگه می‌دارد.
۵. **جدول «بیشترین رشد»** ۳۰ روزه در کنار جدول اصلی.

دامنه‌های `GLOBAL` و `UNIVERSITY` از نمای تجمیعی `user_point_totals` خوانده
می‌شوند (تازه‌سازی هر ۱۵ دقیقه، §7.11). دامنهٔ `OFFERING` مستقیم از دفتر کل
با `offering_id` است: نما ستون ارائه ندارد و یک کلاس کوچک است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, column, exists, func, select, table
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Numeric, Text

from silp.core.exceptions import NotFound, ValidationFailed
from silp.domain.gamification.levels import level_for
from silp.models.education import CourseOffering, Enrollment, Term
from silp.models.gamification import POINT_CATEGORIES, PointEntry
from silp.models.identity import User, UserRole
from silp.models.profile import Profile

SCOPES = ("GLOBAL", "OFFERING", "UNIVERSITY")
#: نقش‌هایی که صاحبانشان در جدول دیگران نیستند — رتبه‌بندی رقابت دانشجویان است.
STAFF_ROLES = ("TA", "INSTRUCTOR", "COORDINATOR", "SUPPORT", "ADMIN")
TOP_N = 10
GROWTH_WINDOW = timedelta(days=30)

# نمای تجمیعی مدل ORM ندارد — فقط خوانده می‌شود.
user_point_totals = table(
    "user_point_totals",
    column("user_id", PGUUID(as_uuid=True)),
    column("term_id", PGUUID(as_uuid=True)),
    column("category", Text),
    column("total", Numeric),
)


@dataclass(frozen=True, slots=True)
class BoardRow:
    rank: int
    user_id: uuid.UUID
    total: Decimal
    level: int


@dataclass(frozen=True, slots=True)
class MyStanding:
    rank: int | None
    total: Decimal
    level: int
    percentile: int | None
    """درصد شرکت‌کنندگانی که امتیازشان کمتر است. برای جمع کمتر از ۵ نفر
    `None` — صدک در کلاس سه‌نفره یعنی رتبهٔ دقیق همه."""
    hidden: bool
    """کاربر در جدول دیگران دیده نمی‌شود — دلیلش `excluded_reason` است."""
    excluded_reason: str | None = None
    """`OPTED_OUT` (انصراف خودش — رتبه‌اش را می‌بیند) یا `STAFF` (کادر
    آموزشی — رتبه ندارد، چون در این رقابت نیست)."""


@dataclass(frozen=True, slots=True)
class Leaderboard:
    scope: str
    scope_id: uuid.UUID | None
    category: str | None
    term_id: uuid.UUID | None
    term_title_fa: str | None
    entries: list[BoardRow]
    growth: list[BoardRow]
    me: MyStanding


MIN_POPULATION_FOR_PERCENTILE = 5


def _now() -> datetime:
    return datetime.now(UTC)


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def board(
        self,
        *,
        viewer_id: uuid.UUID,
        scope: str = "GLOBAL",
        scope_id: uuid.UUID | None = None,
        category: str | None = None,
        limit: int = TOP_N,
        can_view_any_offering: bool = False,
    ) -> Leaderboard:
        if scope not in SCOPES:
            raise ValidationFailed("دامنهٔ رتبه‌بندی معتبر نیست.")
        if category is not None and category not in POINT_CATEGORIES:
            raise ValidationFailed("دستهٔ امتیاز معتبر نیست.")
        size = min(max(limit, 1), TOP_N)

        term = await self.session.scalar(select(Term).where(Term.is_current.is_(True)))
        term_id = term.id if term else None

        if scope == "UNIVERSITY" and scope_id is None:
            scope_id = await self.session.scalar(
                select(Profile.university_id).where(Profile.user_id == viewer_id)
            )
            if scope_id is None:
                raise ValidationFailed("دانشگاهت در نیمرخ ثبت نشده است.")
        if scope == "OFFERING":
            if scope_id is None:
                raise ValidationFailed("برای رتبه‌بندی درس، شناسهٔ ارائه لازم است.")
            if not can_view_any_offering and not await self._in_offering(viewer_id, scope_id):
                # §6.4 قاعدهٔ ۴ — ۴۰۴ به‌جای ۴۰۳: وجود کلاس را هم لو نده.
                raise NotFound("این رتبه‌بندی پیدا نشد.")

        totals = await self._totals(scope, scope_id, category, term_id)
        visible = await self._visible_users(
            [uid for uid, _ in totals] + [viewer_id], scope_id if scope == "UNIVERSITY" else None
        )

        mine = dict(totals).get(viewer_id, Decimal(0))
        field = [(uid, t) for uid, t in totals if uid in visible and t > 0]
        viewer_hidden = viewer_id not in visible
        reason = await self._exclusion_reason(viewer_id) if viewer_hidden else None
        if mine > 0 and reason == "OPTED_OUT":
            field.append((viewer_id, mine))
        ranked = _rank(field)

        top = [row for row in ranked if row[0] in visible][:size]
        growth = await self._growth(scope, scope_id, category, term_id, visible, size)
        lifetime = await self._lifetime(
            {uid for uid, _, _ in top} | {uid for uid, _, _ in growth} | {viewer_id}
        )

        my_rank = next((r for uid, _, r in ranked if uid == viewer_id), None)
        population = len(ranked)
        percentile = None
        if my_rank is not None and population >= MIN_POPULATION_FOR_PERCENTILE:
            below = sum(1 for _, t, _ in ranked if t < mine)
            percentile = round(100 * below / population)

        def rows(items: list[tuple[uuid.UUID, Decimal, int]]) -> list[BoardRow]:
            return [
                BoardRow(rank=r, user_id=uid, total=t, level=level_for(lifetime.get(uid, 0)))
                for uid, t, r in items
            ]

        return Leaderboard(
            scope=scope,
            scope_id=scope_id,
            category=category,
            term_id=term_id,
            term_title_fa=term.title_fa if term else None,
            entries=rows(top),
            growth=rows(growth),
            me=MyStanding(
                rank=my_rank,
                total=mine,
                level=level_for(lifetime.get(viewer_id, 0)),
                percentile=percentile,
                hidden=viewer_hidden,
                excluded_reason=reason,
            ),
        )

    # ── درونی ──────────────────────────────────────────────────────────
    async def _totals(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        category: str | None,
        term_id: uuid.UUID | None,
    ) -> list[tuple[uuid.UUID, Decimal]]:
        query: Select[tuple[uuid.UUID, Decimal]]
        if scope == "OFFERING":
            query = select(PointEntry.user_id, func.sum(PointEntry.amount)).where(
                PointEntry.offering_id == scope_id
            )
            if category is not None:
                query = query.where(PointEntry.category == category)
            query = query.group_by(PointEntry.user_id)
        else:
            if term_id is None:
                # بدون نیم‌سال جاری، رتبه‌بندی «محدود به نیم‌سال» معنایی ندارد.
                return []
            t = user_point_totals.c
            query = select(t.user_id, func.sum(t.total)).where(t.term_id == term_id)
            if category is not None:
                query = query.where(t.category == category)
            query = query.group_by(t.user_id)
        return [(uid, total or Decimal(0)) for uid, total in await self.session.execute(query)]

    async def _visible_users(
        self, user_ids: list[uuid.UUID], university_id: uuid.UUID | None
    ) -> set[uuid.UUID]:
        """کاربرانی که در جدول دیگران دیده می‌شوند: فعال، با نیمرخ، بدون انصراف،
        و **نه کادر آموزشی و مدیریتی**.

        جدول رتبه‌بندی رقابت دانشجویان است. استاد و مدیر هم برای تکمیل نیمرخ
        امتیاز می‌گیرند، و بدون این شرط، کسی که کلاس را درس می‌دهد در جدول
        همان کلاس رتبهٔ دوم می‌شد. استادِ یک ارائه نقشش را از
        `course_offerings.instructor_id` می‌گیرد، نه از `user_roles` (§6.1).
        """
        if not user_ids:
            return set()
        query = (
            select(User.id)
            .join(Profile, Profile.user_id == User.id)
            .where(
                User.id.in_(set(user_ids)),
                User.deleted_at.is_(None),
                User.status == "ACTIVE",
                Profile.show_in_leaderboard.is_(True),
                ~exists().where(UserRole.user_id == User.id, UserRole.role_code.in_(STAFF_ROLES)),
                ~exists().where(
                    CourseOffering.instructor_id == User.id, CourseOffering.deleted_at.is_(None)
                ),
            )
        )
        if university_id is not None:
            query = query.where(Profile.university_id == university_id)
        return set(await self.session.scalars(query))

    async def _exclusion_reason(self, user_id: uuid.UUID) -> str:
        """چرا این کاربر در جدول دیگران نیست؟ کادر آموزشی، وگرنه انصراف خودش."""
        return "STAFF" if await self._is_staff(user_id) else "OPTED_OUT"

    async def _is_staff(self, user_id: uuid.UUID) -> bool:
        role = await self.session.scalar(
            select(UserRole.role_code).where(
                UserRole.user_id == user_id, UserRole.role_code.in_(STAFF_ROLES)
            )
        )
        if role is not None:
            return True
        teaches = await self.session.scalar(
            select(CourseOffering.id).where(
                CourseOffering.instructor_id == user_id, CourseOffering.deleted_at.is_(None)
            )
        )
        return teaches is not None

    async def _growth(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        category: str | None,
        term_id: uuid.UUID | None,
        visible: set[uuid.UUID],
        size: int,
    ) -> list[tuple[uuid.UUID, Decimal, int]]:
        """§9.7 قاعدهٔ ۵ — بیشترین رشد ۳۰ روز اخیر در نیم‌سال جاری."""
        query = select(PointEntry.user_id, func.sum(PointEntry.amount)).where(
            PointEntry.created_at >= _now() - GROWTH_WINDOW
        )
        if scope == "OFFERING":
            query = query.where(PointEntry.offering_id == scope_id)
        elif term_id is not None:
            query = query.where(PointEntry.term_id == term_id)
        else:
            return []
        if category is not None:
            query = query.where(PointEntry.category == category)
        rows = [
            (uid, total)
            for uid, total in await self.session.execute(query.group_by(PointEntry.user_id))
            if total and total > 0
        ]
        # دیده‌پذیری در این مجموعه جداگانه سنجیده می‌شود: کسی که ۳۰ روز اخیر
        # رشد کرده ممکن است در فهرست کل نیم‌سال نیامده باشد.
        allowed = await self._visible_users(
            [uid for uid, _ in rows], scope_id if scope == "UNIVERSITY" else None
        )
        return _rank([(uid, t) for uid, t in rows if uid in allowed])[:size]

    async def _lifetime(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        rows = await self.session.execute(
            select(PointEntry.user_id, func.sum(PointEntry.amount))
            .where(PointEntry.user_id.in_(user_ids))
            .group_by(PointEntry.user_id)
        )
        return {uid: total or Decimal(0) for uid, total in rows}

    async def _in_offering(self, user_id: uuid.UUID, offering_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Enrollment.id).where(
                Enrollment.offering_id == offering_id,
                Enrollment.student_id == user_id,
                Enrollment.status.in_(("ACTIVE", "COMPLETED")),
            )
        )
        return found is not None


def _rank(rows: list[tuple[uuid.UUID, Decimal]]) -> list[tuple[uuid.UUID, Decimal, int]]:
    """رتبهٔ رقابتی (۱، ۲، ۲، ۴) — هم‌امتیازها هم‌رتبه‌اند.

    ترتیب درون هم‌امتیازها با شناسه است تا پاسخ پایدار بماند و با هر
    بارگذاری جابه‌جا نشود.
    """
    ordered = sorted(rows, key=lambda r: (-r[1], r[0]))
    ranked: list[tuple[uuid.UUID, Decimal, int]] = []
    previous: Decimal | None = None
    rank = 0
    for position, (uid, total) in enumerate(ordered, start=1):
        if total != previous:
            rank = position
            previous = total
        ranked.append((uid, total, rank))
    return ranked


__all__ = ["SCOPES", "BoardRow", "Leaderboard", "LeaderboardService", "MyStanding"]
