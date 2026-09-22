"""دفتر کل امتیاز — PRD §9.9، FR-GAM-01/02، M5-03 و M5-08.

سه عمل نوشتن، و هیچ‌کدام ردیفی را ویرایش یا حذف نمی‌کند (D-09):

| عمل | کار |
|-----|-----|
| `award` | یک ردیف اصلی؛ تکرار همان رویداد `None` برمی‌گرداند |
| `reverse` | ردیف معکوس با `amount` منفی و `reverses_id` |
| `reconcile` | وضعیت مطلوب یک محدوده را با دفتر کل هم‌تراز می‌کند |

## چرا `reconcile`

بعضی امتیازها تابع **وضعیت**‌اند، نه یک رویداد یک‌باره: «بهترین تلاش
آزمون» با تلاش بعدی عوض می‌شود (§7.12)، نمرهٔ تشریحی بعداً داده می‌شود،
اعتراض پذیرفته می‌شود، استاد تلاشی را باطل می‌کند، حضوری اصلاح می‌شود و
زنجیرهٔ حضور می‌شکند. برای هرکدام «چه چیزی باید در دفتر باشد» را حساب
می‌کنیم و `reconcile` تفاوت را با معکوس و ثبت دوباره می‌بندد. اجرای
دوباره‌اش هیچ اثری ندارد — شرط کارهای پس‌زمینه (§7.11).

تفاوت با **ضریب** سنجیده می‌شود، نه با مبلغ: اگر مدیر پایهٔ قاعده را عوض
کرده باشد، `reconcile` نباید بی‌صدا گذشته را بازمحاسبه کند (FR-GAM-02
«تغییر قاعده گذشته‌نگر نیست مگر مدیر صریحاً بازمحاسبه کند»).

## سقف‌ها

سقف‌ها **تعداد اعطا** در پنجره‌اند (ADR-0012) — روز و هفتهٔ محلی تهران.
دو اعطای هم‌زمان نباید هر دو از زیر سقف رد شوند، پس پیش از شمارش قفل
مشاوره‌ای تراکنشی `(کاربر)` گرفته می‌شود.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, exists, func, literal, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Exists

from silp.core.exceptions import Conflict, NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.domain.gamification import formulas
from silp.domain.gamification.levels import LevelProgress, progress
from silp.models.education import CourseOffering, Term
from silp.models.gamification import POINT_CATEGORIES, PointEntry, PointRule

log = get_logger("silp.points")

#: کلید یک منبع امتیاز در دفتر کل: (قاعده، نوع منبع، شناسهٔ منبع).
SourceKey = tuple[str, str, uuid.UUID]

MAX_LEDGER_PAGE = 100
RECENT_LIMIT = 5


@dataclass(frozen=True, slots=True)
class Award:
    """یک امتیاز مطلوب — ورودی `award` و `reconcile`."""

    rule_code: str
    source_type: str
    source_id: uuid.UUID
    multiplier: Decimal = Decimal(1)
    category: str | None = None
    """بازنویسی دستهٔ قاعده — برای قواعد پروژه‌ای که دسته از نوع پروژه است."""
    offering_id: uuid.UUID | None = None
    note: str | None = None

    @property
    def key(self) -> SourceKey:
        return (self.rule_code, self.source_type, self.source_id)


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    awarded: tuple[PointEntry, ...] = ()
    reversed: tuple[PointEntry, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.awarded or self.reversed)


@dataclass(frozen=True, slots=True)
class PointsSummary:
    level: LevelProgress
    by_category: dict[str, Decimal]
    term_total: Decimal
    term_by_category: dict[str, Decimal]
    term_id: uuid.UUID | None
    recent: list[PointEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    rule_code: str
    reversed: int
    reawarded: int
    users: int


def _now() -> datetime:
    return datetime.now(UTC)


def _is_idempotency_clash(exc: IntegrityError) -> bool:
    message = str(exc.orig)
    return "idx_point_idempotency" in message or "idx_point_single_reversal" in message


class PointsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._rules: dict[str, PointRule | None] = {}
        self._offering_terms: dict[uuid.UUID, uuid.UUID | None] = {}
        self._current_term: tuple[uuid.UUID | None] | None = None

    # ── قواعد ──────────────────────────────────────────────────────────
    async def rule(self, code: str) -> PointRule | None:
        if code not in self._rules:
            self._rules[code] = await self.session.get(PointRule, code)
        return self._rules[code]

    async def rules(self) -> list[PointRule]:
        rows = await self.session.scalars(
            select(PointRule).order_by(PointRule.category, PointRule.code)
        )
        return list(rows)

    async def update_rule(
        self,
        code: str,
        *,
        title_fa: str | None = None,
        base_points: Decimal | None = None,
        daily_cap: int | None = None,
        weekly_cap: int | None = None,
        term_cap: int | None = None,
        is_active: bool | None = None,
        clear_caps: Sequence[str] = (),
    ) -> PointRule:
        """FR-GAM-02 — تغییر قاعده **گذشته‌نگر نیست**؛ بازمحاسبه عمل جداست."""
        rule = await self.session.get(PointRule, code)
        if rule is None:
            raise NotFound("این قاعدهٔ امتیاز پیدا نشد.")
        if base_points is not None:
            if base_points < 0:
                raise ValidationFailed("امتیاز پایه نمی‌تواند منفی باشد.")
            rule.base_points = base_points
        if title_fa is not None:
            if not title_fa.strip():
                raise ValidationFailed("عنوان قاعده خالی است.")
            rule.title_fa = title_fa.strip()
        for name, value in (
            ("daily_cap", daily_cap),
            ("weekly_cap", weekly_cap),
            ("term_cap", term_cap),
        ):
            if value is not None:
                if value < 1:
                    raise ValidationFailed("سقف باید دست‌کم ۱ باشد؛ برای برداشتن سقف، خالی‌اش کنید.")
                setattr(rule, name, value)
        for name in clear_caps:
            if name not in ("daily_cap", "weekly_cap", "term_cap"):
                raise ValidationFailed(f"سقف ناشناخته: {name}")
            setattr(rule, name, None)
        if is_active is not None:
            rule.is_active = is_active
        await self.session.commit()
        self._rules.pop(code, None)
        log.info("point_rule_updated", rule_code=code)
        return rule

    # ── نیم‌سال ────────────────────────────────────────────────────────
    async def term_for(self, offering_id: uuid.UUID | None) -> uuid.UUID | None:
        """نیم‌سال امتیاز: نیم‌سال ارائه، وگرنه نیم‌سال جاری، وگرنه هیچ."""
        if offering_id is not None:
            if offering_id not in self._offering_terms:
                self._offering_terms[offering_id] = await self.session.scalar(
                    select(CourseOffering.term_id).where(CourseOffering.id == offering_id)
                )
            term = self._offering_terms[offering_id]
            if term is not None:
                return term
        return await self.current_term_id()

    async def current_term_id(self) -> uuid.UUID | None:
        if self._current_term is None:
            current = await self.session.scalar(select(Term.id).where(Term.is_current.is_(True)))
            self._current_term = (current,)
        return self._current_term[0]

    # ── نوشتن ──────────────────────────────────────────────────────────
    async def award(
        self,
        user_id: uuid.UUID,
        award: Award,
        *,
        revision: int = 0,
        term_id: uuid.UUID | None = None,
        ignore_caps: bool = False,
    ) -> PointEntry | None:
        """ثبت امتیاز — §9.9. تکرار همان رویداد، قاعدهٔ غیرفعال، مبلغ صفر،
        و رسیدن به سقف، همه `None` برمی‌گردانند؛ هیچ‌کدام خطا نیستند."""
        rule = await self.rule(award.rule_code)
        if rule is None or not rule.is_active:
            return None
        multiplier = formulas.quantize_multiplier(award.multiplier)
        if multiplier <= 0:
            return None
        amount = formulas.amount_of(rule.base_points, multiplier)
        if amount <= 0:
            return None

        term = term_id or await self.term_for(award.offering_id)
        if not ignore_caps and await self._cap_reached(user_id, rule, term):
            log.info("points_cap_reached", user_id=str(user_id), rule_code=rule.code)
            return None

        entry = PointEntry(
            user_id=user_id,
            category=award.category or rule.category,
            rule_code=rule.code,
            amount=amount,
            multiplier=multiplier,
            source_type=award.source_type,
            source_id=award.source_id,
            revision=revision,
            term_id=term,
            offering_id=award.offering_id,
            note=award.note,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(entry)
                await self.session.flush()
        except IntegrityError as exc:
            if not _is_idempotency_clash(exc):
                raise
            # کلید بی‌اثری — همین رویداد قبلاً امتیاز گرفته است.
            return None
        log.info(
            "points_awarded",
            user_id=str(user_id),
            rule_code=rule.code,
            amount=str(amount),
            source_type=award.source_type,
        )
        return entry

    async def reverse(self, entry: PointEntry, reason: str) -> PointEntry | None:
        """اصلاح با رکورد معکوس — هرگز حذف یا ویرایش (D-09).

        معکوسِ یک ردیف یک‌بار ممکن است (`idx_point_single_reversal`)؛ تلاش
        دوم `None` برمی‌گرداند.
        """
        if entry.reverses_id is not None:
            raise Conflict("رکورد معکوس خودش معکوس نمی‌شود.")
        reversal = PointEntry(
            user_id=entry.user_id,
            category=entry.category,
            rule_code=entry.rule_code,
            amount=-entry.amount,
            multiplier=entry.multiplier,
            source_type=entry.source_type,
            source_id=entry.source_id,
            revision=entry.revision,
            term_id=entry.term_id,
            offering_id=entry.offering_id,
            note=reason,
            reverses_id=entry.id,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(reversal)
                await self.session.flush()
        except IntegrityError as exc:
            if not _is_idempotency_clash(exc):
                raise
            return None
        log.info(
            "points_reversed",
            user_id=str(entry.user_id),
            rule_code=entry.rule_code,
            amount=str(entry.amount),
        )
        return reversal

    async def reconcile(
        self,
        user_id: uuid.UUID,
        *,
        desired: Iterable[Award],
        universe: Iterable[SourceKey],
        reason: str,
    ) -> ReconcileResult:
        """دفتر کل را در محدودهٔ `universe` با `desired` هم‌تراز می‌کند.

        `universe` همهٔ کلیدهایی است که این فراخوانی مسئولشان است — ردیف
        فعالی بیرون از آن دست نمی‌خورد، حتی اگر در `desired` نباشد.
        """
        wanted = {a.key: a for a in desired}
        scope = set(universe) | set(wanted)
        if not scope:
            return ReconcileResult()

        await self._lock_user(user_id)
        active = await self._active_entries(user_id, scope)
        revisions = await self._revision_counts(user_id, scope)

        awarded: list[PointEntry] = []
        reversed_: list[PointEntry] = []
        satisfied: set[SourceKey] = set()
        for entry in active:
            key: SourceKey = (entry.rule_code, entry.source_type, entry.source_id)  # type: ignore[assignment]
            target = wanted.get(key)
            if (
                target is not None
                and key not in satisfied
                and entry.multiplier == (formulas.quantize_multiplier(target.multiplier))
            ):
                satisfied.add(key)
                continue
            reversal = await self.reverse(entry, reason)
            if reversal is not None:
                reversed_.append(reversal)

        for key, target in wanted.items():
            if key in satisfied:
                continue
            created = await self.award(user_id, target, revision=revisions.get(key, 0))
            if created is not None:
                awarded.append(created)
        return ReconcileResult(awarded=tuple(awarded), reversed=tuple(reversed_))

    async def recalculate(
        self,
        rule_code: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> RecalculationResult:
        """بازمحاسبهٔ گذشته‌نگر — §9.9، M5-08.

        برای هر ردیف فعال این قاعده در بازه: معکوس، و اگر قاعده هنوز فعال
        است، ثبت دوباره با `پایهٔ جدید × ضریب اصلی` و `revision` بعدی. همه
        در تراکنش فراخواننده. **هیچ ردیفی پاک نمی‌شود.**

        سقف‌ها دوباره اعمال نمی‌شوند: بازمحاسبه قیمت رویدادهای گذشته را عوض
        می‌کند، نه اینکه کدام رویداد امتیاز بگیرد.
        """
        rule = await self.session.get(PointRule, rule_code)
        if rule is None:
            raise NotFound("این قاعدهٔ امتیاز پیدا نشد.")
        self._rules[rule_code] = rule

        conditions = [
            PointEntry.rule_code == rule_code,
            PointEntry.reverses_id.is_(None),
            ~self._is_reversed(),
        ]
        if since is not None:
            conditions.append(PointEntry.created_at >= since)
        if until is not None:
            conditions.append(PointEntry.created_at < until)
        entries = list(
            await self.session.scalars(
                select(PointEntry).where(*conditions).order_by(PointEntry.created_at)
            )
        )

        reversed_count = 0
        reawarded = 0
        users: set[uuid.UUID] = set()
        for entry in entries:
            new_amount = formulas.amount_of(rule.base_points, entry.multiplier)
            if rule.is_active and new_amount == entry.amount:
                continue
            if await self.reverse(entry, "بازمحاسبه با قاعدهٔ جدید") is None:
                continue
            reversed_count += 1
            users.add(entry.user_id)
            if not rule.is_active or entry.source_id is None:
                continue
            again = await self.award(
                entry.user_id,
                Award(
                    rule_code=rule_code,
                    source_type=entry.source_type,
                    source_id=entry.source_id,
                    multiplier=entry.multiplier,
                    category=entry.category,
                    offering_id=entry.offering_id,
                    note=entry.note,
                ),
                revision=entry.revision + 1,
                term_id=entry.term_id,
                ignore_caps=True,
            )
            if again is not None:
                reawarded += 1

        log.info(
            "points_recalculated",
            rule_code=rule_code,
            reversed=reversed_count,
            reawarded=reawarded,
            users=len(users),
        )
        return RecalculationResult(
            rule_code=rule_code, reversed=reversed_count, reawarded=reawarded, users=len(users)
        )

    async def reverse_by_id(self, entry_id: uuid.UUID, reason: str) -> PointEntry:
        """اصلاح دستی مدیر — یک ردیف مشخص."""
        cleaned = reason.strip()
        if not cleaned:
            raise ValidationFailed("دلیل اصلاح امتیاز اجباری است.")
        entry = await self.session.get(PointEntry, entry_id)
        if entry is None:
            raise NotFound("این ردیف امتیاز پیدا نشد.")
        reversal = await self.reverse(entry, cleaned)
        if reversal is None:
            raise Conflict("این ردیف قبلاً اصلاح شده است.")
        return reversal

    # ── خواندن ─────────────────────────────────────────────────────────
    async def summary(self, user_id: uuid.UUID) -> PointsSummary:
        """امتیاز کل، سطح، و امتیاز نیم‌سال — از خود دفتر کل، نه از نمای تجمیعی.

        نمای تجمیعی ۱۵ دقیقه کهنه است (§7.11). دانشجویی که همین حالا
        تحویل‌دادنی‌اش تأیید شد و Toast «+۵۰» دید، نباید در هدر عدد قدیمی
        ببیند.
        """
        term_id = await self.current_term_id()
        rows = list(
            await self.session.execute(
                select(PointEntry.category, PointEntry.term_id, func.sum(PointEntry.amount))
                .where(PointEntry.user_id == user_id)
                .group_by(PointEntry.category, PointEntry.term_id)
            )
        )
        by_category = {c: Decimal(0) for c in POINT_CATEGORIES}
        term_by_category = {c: Decimal(0) for c in POINT_CATEGORIES}
        for category, entry_term, total in rows:
            by_category[category] += total or Decimal(0)
            if term_id is not None and entry_term == term_id:
                term_by_category[category] += total or Decimal(0)

        recent = list(
            await self.session.scalars(
                select(PointEntry)
                .where(PointEntry.user_id == user_id)
                .order_by(PointEntry.id.desc())
                .limit(RECENT_LIMIT)
            )
        )
        lifetime = sum(by_category.values(), Decimal(0))
        return PointsSummary(
            level=progress(lifetime),
            by_category=by_category,
            term_total=sum(term_by_category.values(), Decimal(0)),
            term_by_category=term_by_category,
            term_id=term_id,
            recent=recent,
        )

    async def ledger(
        self,
        user_id: uuid.UUID,
        *,
        category: str | None = None,
        source_type: str | None = None,
        source_id: uuid.UUID | None = None,
        before: uuid.UUID | None = None,
        limit: int = 30,
    ) -> tuple[list[PointEntry], uuid.UUID | None]:
        """دفتر کل شخصی، تازه‌ترین اول — کرسر همان شناسهٔ UUIDv7 است.

        شناسهٔ UUIDv7 با زمان مرتب است، پس «قبل از این شناسه» همان «قبل از
        این لحظه» است بدون ستون زمان در کرسر.
        """
        if category is not None and category not in POINT_CATEGORIES:
            raise ValidationFailed("دستهٔ امتیاز معتبر نیست.")
        size = min(max(limit, 1), MAX_LEDGER_PAGE)
        query = select(PointEntry).where(PointEntry.user_id == user_id)
        if category is not None:
            query = query.where(PointEntry.category == category)
        if source_type is not None:
            query = query.where(PointEntry.source_type == source_type)
        if source_id is not None:
            query = query.where(PointEntry.source_id == source_id)
        if before is not None:
            query = query.where(PointEntry.id < before)
        rows = list(
            await self.session.scalars(query.order_by(PointEntry.id.desc()).limit(size + 1))
        )
        has_more = len(rows) > size
        page = rows[:size]
        return page, (page[-1].id if has_more and page else None)

    async def reversed_ids(self, entry_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """کدام ردیف‌های اصلی معکوس شده‌اند — برای خط‌خوردن در دفتر کل."""
        if not entry_ids:
            return set()
        rows = await self.session.scalars(
            select(PointEntry.reverses_id).where(PointEntry.reverses_id.in_(entry_ids))
        )
        return {r for r in rows if r is not None}

    async def refresh_totals(self) -> None:
        """§7.11 `refresh_point_totals` — بدون قفل خواندن جدول رتبه‌بندی."""
        await self.session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY user_point_totals"))

    # ── درونی ──────────────────────────────────────────────────────────
    @staticmethod
    def _is_reversed() -> Exists:
        """«این ردیف اصلی معکوس شده است» — همبسته با `PointEntry` بیرونی."""
        reversal = aliased(PointEntry)
        return exists().where(reversal.reverses_id == PointEntry.id)

    async def _lock_user(self, user_id: uuid.UUID) -> None:
        """قفل مشاوره‌ای تا پایان تراکنش — سقف و `reconcile` هم‌زمان را صف می‌کند."""
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(literal(f"points:{user_id}"), 0))
            )
        )

    async def _active_entries(self, user_id: uuid.UUID, scope: set[SourceKey]) -> list[PointEntry]:
        rows = await self.session.scalars(
            select(PointEntry)
            .where(
                PointEntry.user_id == user_id,
                PointEntry.reverses_id.is_(None),
                tuple_(PointEntry.rule_code, PointEntry.source_type, PointEntry.source_id).in_(
                    list(scope)
                ),
                ~self._is_reversed(),
            )
            .order_by(PointEntry.id)
        )
        return list(rows)

    async def _revision_counts(
        self, user_id: uuid.UUID, scope: set[SourceKey]
    ) -> dict[SourceKey, int]:
        """شمارهٔ بازنگری بعدی هر کلید = بیشینهٔ فعلی + ۱."""
        rows = await self.session.execute(
            select(
                PointEntry.rule_code,
                PointEntry.source_type,
                PointEntry.source_id,
                func.max(PointEntry.revision),
            )
            .where(
                PointEntry.user_id == user_id,
                PointEntry.reverses_id.is_(None),
                tuple_(PointEntry.rule_code, PointEntry.source_type, PointEntry.source_id).in_(
                    list(scope)
                ),
            )
            .group_by(PointEntry.rule_code, PointEntry.source_type, PointEntry.source_id)
        )
        result: dict[SourceKey, int] = defaultdict(int)
        for rule_code, source_type, source_id, highest in rows:
            result[(rule_code, source_type, source_id)] = int(highest) + 1
        return result

    async def _cap_reached(
        self, user_id: uuid.UUID, rule: PointRule, term_id: uuid.UUID | None
    ) -> bool:
        windows: list[tuple[int, ColumnElement[bool]]] = []
        now = _now()
        if rule.daily_cap is not None:
            windows.append((rule.daily_cap, PointEntry.created_at >= formulas.local_day_start(now)))
        if rule.weekly_cap is not None:
            windows.append(
                (rule.weekly_cap, PointEntry.created_at >= formulas.local_week_start(now))
            )
        if rule.term_cap is not None and term_id is not None:
            windows.append((rule.term_cap, PointEntry.term_id == term_id))
        if not windows:
            return False

        await self._lock_user(user_id)
        for cap, condition in windows:
            used = await self.session.scalar(
                select(func.count())
                .select_from(PointEntry)
                .where(
                    and_(
                        PointEntry.user_id == user_id,
                        PointEntry.rule_code == rule.code,
                        PointEntry.reverses_id.is_(None),
                        ~self._is_reversed(),
                        condition,
                    )
                )
            )
            if (used or 0) >= cap:
                return True
        return False


__all__ = [
    "Award",
    "PointsService",
    "PointsSummary",
    "RecalculationResult",
    "ReconcileResult",
    "SourceKey",
]
