"""هماهنگی موتور توصیه‌گر — PRD §8.12.

تقسیم کار طبق سند: **فیلتر در دیتابیس، امتیازدهی در پایتون.** برای مقیاس
فعلی (کمتر از ۵۰۰۰ پروژه) این بهینه است و مهم‌تر اینکه امتیازدهی خالص و
قابل تست می‌ماند.

کش: `rec:{user_id}` با TTL سی دقیقه (§8.12). باطل‌سازی با تغییر نیمرخ،
انتشار پروژهٔ تازه، یا ثبت درخواست.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import Select, Subquery, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.core.redis import get_redis
from silp.domain.recommendation.diversity import DEFAULT_RESULT_SIZE, diversify, ensure_stretch
from silp.domain.recommendation.explainer import with_reasons
from silp.domain.recommendation.schemas import (
    AssetReq,
    Component,
    Goal,
    InterestRef,
    MatchResult,
    ProjectKind,
    ProjectSpec,
    SkillReq,
    StudentContext,
    Verdict,
    Weights,
    WorkStyle,
)
from silp.domain.recommendation.scorer import profile_completeness, score_project
from silp.models.profile import Profile, ProfileAsset, ProfileInterest, ProfileSkill
from silp.models.project import (
    Project,
    ProjectApplication,
    ProjectInterest,
    ProjectRequiredAsset,
    ProjectRequiredSkill,
    RecommendationFeedback,
    Team,
    TeamMember,
)
from silp.models.taxonomy import Asset, Interest, Skill

log = get_logger("silp.recommendation")

REC_CACHE_TTL_SECONDS = 1800  # §8.12 — سی دقیقه
# سقف نامزدهایی که امتیاز می‌گیرند. بالاتر از این، هزینهٔ محاسبه بی‌فایده
# است چون نتیجهٔ نهایی حداکثر ده موردی است.
CANDIDATE_LIMIT = 300
PREVIEW_SIZE = 3


def key_recommendations(user_id: uuid.UUID) -> str:
    return f"silp:rec:{user_id}"


# ── ساخت زمینهٔ دانشجو ─────────────────────────────────────────────────
async def load_student_context(session: AsyncSession, user_id: uuid.UUID) -> StudentContext:
    """نیمرخ دانشجو را به ساختار خالص §8.12 تبدیل می‌کند.

    پنج کوئری کوچک به‌جای یک `JOIN` بزرگ: نتیجه یکی است و هر کدام از
    ایندکس خودش استفاده می‌کند.
    """
    profile = await session.get(Profile, user_id)

    skill_rows = (
        await session.execute(
            select(ProfileSkill.skill_id, ProfileSkill.level, ProfileSkill.verified_at).where(
                ProfileSkill.user_id == user_id
            )
        )
    ).all()
    asset_rows = (
        await session.scalars(select(ProfileAsset.asset_id).where(ProfileAsset.user_id == user_id))
    ).all()
    interest_rows = (
        await session.execute(
            select(ProfileInterest.interest_id, ProfileInterest.level).where(
                ProfileInterest.user_id == user_id
            )
        )
    ).all()
    # درخواست پس‌گرفته‌شده مانع پیشنهاد دوباره نیست (§8.12 کوئری نامزد).
    applied_rows = (
        await session.scalars(
            select(ProjectApplication.project_id).where(
                ProjectApplication.applicant_id == user_id,
                ProjectApplication.status != "WITHDRAWN",
            )
        )
    ).all()
    feedback_rows = (
        await session.execute(
            select(RecommendationFeedback.project_id, RecommendationFeedback.verdict).where(
                RecommendationFeedback.user_id == user_id
            )
        )
    ).all()

    return StudentContext(
        user_id=user_id,
        skills={row.skill_id: row.level for row in skill_rows},
        verified_skills=frozenset(
            row.skill_id for row in skill_rows if row.verified_at is not None
        ),
        assets=frozenset(asset_rows),
        interests={row.interest_id: row.level for row in interest_rows},
        weekly_hours=profile.weekly_hours if profile else None,
        work_style=WorkStyle(profile.work_style) if profile and profile.work_style else None,
        primary_goal=Goal(profile.primary_goal) if profile and profile.primary_goal else None,
        # ثبت‌نام در ارائه‌ها در M3 می‌آید؛ تا آن زمان ضریب f_course خاموش است.
        enrolled_offerings=frozenset(),
        completed_steps=profile.survey_completed_steps if profile else 0,
        applied_project_ids=frozenset(applied_rows),
        feedback={row.project_id: Verdict(row.verdict) for row in feedback_rows},
    )


# ── کوئری نامزد ────────────────────────────────────────────────────────
def _active_member_count() -> Subquery:
    """شمار اعضای فعال هر پروژه — پایهٔ شرط «ظرفیت باقی‌مانده» §8.12."""
    return (
        select(Team.project_id.label("project_id"), func.count().label("members"))
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.status == "ACTIVE", Team.project_id.is_not(None))
        .group_by(Team.project_id)
        .subquery()
    )


def candidate_query(ctx: StudentContext, *, now: datetime) -> Select[tuple[Project, int, int]]:
    """فیلتر اولیهٔ §8.12 — همان شرط‌ها، ساخته‌شده با SQLAlchemy.

    چهار شرط: باز بودن، مهلت، ظرفیت باقی‌مانده، و داشتن همهٔ امکانات
    الزامی. سه شرط اول در سند صریح‌اند؛ شرط چهارم دروازهٔ §8.3 است و
    عمداً در SQL اعمال می‌شود، نه پس از واکشی — پروژه‌ای که دانشجو
    نمی‌تواند انجام دهد نباید اصلاً امتیاز بگیرد.
    """
    members = _active_member_count()

    member_count = func.coalesce(members.c.members, 0)
    pending = (
        select(func.count())
        .select_from(ProjectApplication)
        .where(
            ProjectApplication.project_id == Project.id,
            ProjectApplication.status == "PENDING",
        )
        .scalar_subquery()
    )

    stmt = (
        select(Project, member_count.label("active_members"), pending.label("pending_applications"))
        .outerjoin(members, members.c.project_id == Project.id)
        .where(
            Project.status == "OPEN",
            Project.deleted_at.is_(None),
            or_(
                Project.applications_close_at.is_(None),
                Project.applications_close_at > now,
            ),
            member_count < Project.team_size_max,
        )
    )

    # دروازهٔ امکانات فقط پس از گام ۲ اعمال می‌شود — همان قاعدهٔ
    # `scorer.has_all_mandatory_assets`. هر دو باید هم‌نظر بمانند، وگرنه
    # پروژه‌ای که SQL رد کرده در `/projects/{id}` امتیاز می‌گیرد.
    if ctx.has_data_for(Component.ASSET):
        # `NOT IN ()` در SQL نامعتبر است، پس برای دانشجویی که گفته هیچ
        # امکانی ندارد یک شناسهٔ ناموجود می‌گذاریم: شرط به «هر امکان
        # الزامی، کم است» تبدیل می‌شود، که همان معنای درست است.
        owned_assets = ctx.assets or frozenset({uuid.UUID(int=0)})
        stmt = stmt.where(
            ~exists(
                select(1)
                .select_from(ProjectRequiredAsset)
                .where(
                    ProjectRequiredAsset.project_id == Project.id,
                    ProjectRequiredAsset.is_mandatory.is_(True),
                    ProjectRequiredAsset.asset_id.notin_(owned_assets),
                )
            )
        )

    return stmt.order_by(Project.last_activity_at.desc()).limit(CANDIDATE_LIMIT)


async def taxonomy_titles(session: AsyncSession) -> tuple[dict[uuid.UUID, str], ...]:
    """عنوان فارسی مهارت، امکان و علاقه — برای متن دلیل §8.10.

    جدول‌های مرجع کوچک‌اند (۱۷ + ۹ + ۱۲ ردیف)؛ خواندن کاملشان از JOIN
    زدن به هر پروژه ارزان‌تر است.
    """
    skills = {
        row.id: row.title_fa
        for row in (await session.execute(select(Skill.id, Skill.title_fa))).all()
    }
    assets = {
        row.id: row.title_fa
        for row in (await session.execute(select(Asset.id, Asset.title_fa))).all()
    }
    interests = {
        row.id: row.title_fa
        for row in (await session.execute(select(Interest.id, Interest.title_fa))).all()
    }
    return skills, assets, interests


async def load_candidates(
    session: AsyncSession, ctx: StudentContext, *, now: datetime
) -> list[ProjectSpec]:
    """واکشی نامزدها و تبدیلشان به `ProjectSpec` خالص."""
    rows = (await session.execute(candidate_query(ctx, now=now))).all()
    if not rows:
        return []

    project_ids = [row[0].id for row in rows]
    skill_titles, asset_titles, interest_titles = await taxonomy_titles(session)

    req_skills: dict[uuid.UUID, list[SkillReq]] = {pid: [] for pid in project_ids}
    for skill_row in await session.scalars(
        select(ProjectRequiredSkill).where(ProjectRequiredSkill.project_id.in_(project_ids))
    ):
        req_skills[skill_row.project_id].append(
            SkillReq(
                skill_id=skill_row.skill_id,
                title_fa=skill_titles.get(skill_row.skill_id, "مهارت"),
                min_level=skill_row.min_level,
                weight=skill_row.weight,
                is_teachable=skill_row.is_teachable,
            )
        )

    req_assets: dict[uuid.UUID, list[AssetReq]] = {pid: [] for pid in project_ids}
    for asset_row in await session.scalars(
        select(ProjectRequiredAsset).where(ProjectRequiredAsset.project_id.in_(project_ids))
    ):
        req_assets[asset_row.project_id].append(
            AssetReq(
                asset_id=asset_row.asset_id,
                title_fa=asset_titles.get(asset_row.asset_id, "امکانات"),
                is_mandatory=asset_row.is_mandatory,
            )
        )

    proj_interests: dict[uuid.UUID, list[InterestRef]] = {pid: [] for pid in project_ids}
    for interest_row in await session.scalars(
        select(ProjectInterest).where(ProjectInterest.project_id.in_(project_ids))
    ):
        proj_interests[interest_row.project_id].append(
            InterestRef(
                interest_id=interest_row.interest_id,
                title_fa=interest_titles.get(interest_row.interest_id, "این حوزه"),
            )
        )

    specs: list[ProjectSpec] = []
    for project, active_members, pending_applications in rows:
        specs.append(
            ProjectSpec(
                id=project.id,
                title_fa=project.title_fa,
                kind=ProjectKind(project.kind),
                difficulty=project.difficulty,
                work_style=WorkStyle(project.work_style),
                time_commitment_hpw=project.time_commitment_hpw,
                team_size_min=project.team_size_min,
                team_size_max=project.team_size_max,
                active_members=int(active_members or 0),
                required_skills=tuple(req_skills[project.id]),
                required_assets=tuple(req_assets[project.id]),
                interests=tuple(proj_interests[project.id]),
                offering_id=project.offering_id,
                # عنوان درس در M3 پر می‌شود؛ متن دلیل تا آن زمان جملهٔ
                # جایگزین §8.10 را به کار می‌برد.
                offering_title_fa=None,
                published_at=project.created_at,
                applications_close_at=project.applications_close_at,
                deadline_on=project.deadline_on,
                pending_applications=int(pending_applications or 0),
            )
        )
    return specs


async def spec_for_project(session: AsyncSession, project: Project) -> ProjectSpec:
    """ساخت `ProjectSpec` برای **یک** پروژه — برای صفحهٔ جزئیات.

    `load_candidates` برای فهرست ساخته شده و صدها ردیف را دسته‌ای می‌خواند؛
    استفاده از آن برای یک پروژه یعنی پیمایش کل بانک برای یک صفحه.
    """
    skill_titles, asset_titles, interest_titles = await taxonomy_titles(session)

    active_members = (
        await session.scalar(
            select(func.count())
            .select_from(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project.id, TeamMember.status == "ACTIVE")
        )
        or 0
    )
    pending = (
        await session.scalar(
            select(func.count())
            .select_from(ProjectApplication)
            .where(
                ProjectApplication.project_id == project.id,
                ProjectApplication.status == "PENDING",
            )
        )
        or 0
    )

    return ProjectSpec(
        id=project.id,
        title_fa=project.title_fa,
        kind=ProjectKind(project.kind),
        difficulty=project.difficulty,
        work_style=WorkStyle(project.work_style),
        time_commitment_hpw=project.time_commitment_hpw,
        team_size_min=project.team_size_min,
        team_size_max=project.team_size_max,
        active_members=int(active_members),
        required_skills=tuple(
            SkillReq(
                skill_id=r.skill_id,
                title_fa=skill_titles.get(r.skill_id, "مهارت"),
                min_level=r.min_level,
                weight=r.weight,
                is_teachable=r.is_teachable,
            )
            for r in project.required_skills
        ),
        required_assets=tuple(
            AssetReq(
                asset_id=r.asset_id,
                title_fa=asset_titles.get(r.asset_id, "امکانات"),
                is_mandatory=r.is_mandatory,
            )
            for r in project.required_assets
        ),
        interests=tuple(
            InterestRef(
                interest_id=r.interest_id,
                title_fa=interest_titles.get(r.interest_id, "این حوزه"),
            )
            for r in project.interests
        ),
        offering_id=project.offering_id,
        offering_title_fa=None,
        published_at=project.created_at,
        applications_close_at=project.applications_close_at,
        deadline_on=project.deadline_on,
        pending_applications=int(pending),
    )


# ── محاسبهٔ پیشنهادها ──────────────────────────────────────────────────
def rank(
    ctx: StudentContext,
    specs: list[ProjectSpec],
    *,
    now: datetime,
    weights: Weights | None = None,
    limit: int = DEFAULT_RESULT_SIZE,
) -> list[MatchResult]:
    """امتیازدهی، حذف موارد کنارگذاشته، مرتب‌سازی، و بازچینش — منطق خالص."""
    scored = [score_project(ctx, spec, weights, now=now) for spec in specs]
    eligible = [m for m in scored if not m.is_excluded]
    eligible.sort(key=lambda m: (-m.score, str(m.project.id)))

    chosen = diversify(eligible, limit)
    chosen = ensure_stretch(chosen, eligible, limit)
    return [with_reasons(ctx, m) for m in chosen]


async def recommend(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = DEFAULT_RESULT_SIZE,
    now: datetime | None = None,
    use_cache: bool = True,
) -> tuple[list[MatchResult], float, datetime]:
    """پیشنهادهای یک دانشجو. خروجی: (نتایج، کامل بودن نیمرخ، زمان محاسبه)."""
    now = now or datetime.now(UTC)
    ctx = await load_student_context(session, user_id)

    # کش همیشه `DEFAULT_RESULT_SIZE` مورد نگه می‌دارد. اگر درخواست بیش از
    # آن باشد، کش جوابگو نیست و از نو محاسبه می‌شود.
    if use_cache and limit <= DEFAULT_RESULT_SIZE:
        cached = await _read_cache(user_id)
        if cached is not None:
            results, computed_at = cached
            return results[:limit], profile_completeness(ctx), computed_at

    specs = await load_candidates(session, ctx, now=now)
    results = rank(ctx, specs, now=now, limit=max(limit, DEFAULT_RESULT_SIZE))

    if use_cache:
        await _write_cache(user_id, results, now)

    return results[:limit], profile_completeness(ctx), now


async def preview(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = PREVIEW_SIZE
) -> list[MatchResult]:
    """«لحظهٔ طلایی» §01 — پیشنهاد فوری پس از هر گام ارزیابی.

    کش عمداً دور زده می‌شود: کاربر همین الان نیمرخش را عوض کرده و باید
    اثرش را ببیند.
    """
    results, _, _ = await recommend(session, user_id, limit=limit, use_cache=False)
    return results


# ── بازخورد پیشنهاد ────────────────────────────────────────────────────
async def record_feedback(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    verdict: str,
    reason: str | None = None,
) -> None:
    """§8.9 — ثبت نظر دانشجو دربارهٔ یک پیشنهاد.

    نظر تازه جای قبلی را می‌گیرد: دانشجو باید بتواند نظرش را عوض کند و
    پروژه‌ای را که «دیگر نشانم نده» زده بود، دوباره ببیند.

    `commit` اینجاست، نه در مسیر (§قرارداد `db/session.py`)، و ابطال کش
    **پس از** آن انجام می‌شود تا محاسبهٔ بعدی وضعیت نوشته‌شده را بخواند.
    """
    await session.execute(
        pg_insert(RecommendationFeedback)
        .values(user_id=user_id, project_id=project_id, verdict=verdict, reason=reason)
        .on_conflict_do_update(
            index_elements=[RecommendationFeedback.user_id, RecommendationFeedback.project_id],
            set_={"verdict": verdict, "reason": reason},
        )
    )
    await session.commit()
    await invalidate(user_id)


# ── کش ─────────────────────────────────────────────────────────────────
def _encode(results: list[MatchResult], computed_at: datetime) -> str:
    return json.dumps(
        {
            "computed_at": computed_at.isoformat(),
            "items": [_encode_match(m) for m in results],
        },
        ensure_ascii=False,
        default=str,
    )


def _encode_match(match: MatchResult) -> dict[str, Any]:
    payload = asdict(match)
    payload["project"]["kind"] = match.project.kind.value
    payload["project"]["work_style"] = match.project.work_style.value
    payload["breakdown"] = {k.value: v for k, v in match.breakdown.items()}
    payload["weights"] = {k.value: v for k, v in match.weights.items()}
    payload["reasons"] = [
        {**asdict(r), "type": r.type.value, "polarity": r.polarity.value} for r in match.reasons
    ]
    return payload


async def _read_cache(user_id: uuid.UUID) -> tuple[list[MatchResult], datetime] | None:
    """کش خوانده می‌شود ولی هرگز به رمزگشایی کامل تکیه نمی‌کنیم.

    اگر شکل ذخیره‌شده با نسخهٔ جدید کد نخواند، کش نادیده گرفته می‌شود و
    دوباره محاسبه می‌گردد — بهتر از پاسخ اشتباه.
    """
    try:
        raw = await get_redis().get(key_recommendations(user_id))
    except RedisError as exc:
        log.warning("rec_cache_read_failed", error=str(exc))
        return None
    if not raw:
        return None

    try:
        payload = json.loads(raw)
        return _decode(payload)
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("rec_cache_decode_failed", error=str(exc))
        return None


def _decode(payload: dict[str, Any]) -> tuple[list[MatchResult], datetime]:
    from silp.domain.recommendation.schemas import Polarity, Reason, ReasonType

    computed_at = datetime.fromisoformat(str(payload["computed_at"]))
    items: list[MatchResult] = []
    for raw_item in payload["items"]:
        item = dict(raw_item)
        project_payload = dict(item["project"])
        project_payload["id"] = uuid.UUID(str(project_payload["id"]))
        project_payload["kind"] = ProjectKind(project_payload["kind"])
        project_payload["work_style"] = WorkStyle(project_payload["work_style"])
        project_payload["required_skills"] = tuple(
            SkillReq(**{**r, "skill_id": uuid.UUID(str(r["skill_id"]))})
            for r in project_payload["required_skills"]
        )
        project_payload["required_assets"] = tuple(
            AssetReq(**{**r, "asset_id": uuid.UUID(str(r["asset_id"]))})
            for r in project_payload["required_assets"]
        )
        project_payload["interests"] = tuple(
            InterestRef(**{**r, "interest_id": uuid.UUID(str(r["interest_id"]))})
            for r in project_payload["interests"]
        )
        for field_name in ("published_at", "applications_close_at"):
            value = project_payload.get(field_name)
            project_payload[field_name] = datetime.fromisoformat(value) if value else None
        project_payload["offering_id"] = (
            uuid.UUID(str(project_payload["offering_id"]))
            if project_payload.get("offering_id")
            else None
        )
        project_payload["deadline_on"] = None

        items.append(
            MatchResult(
                project=ProjectSpec(**project_payload),
                score=float(item["score"]),
                base_score=float(item["base_score"]),
                breakdown={Component(k): float(v) for k, v in item["breakdown"].items()},
                weights={Component(k): float(v) for k, v in item["weights"].items()},
                factors={k: float(v) for k, v in item["factors"].items()},
                reasons=tuple(
                    Reason(
                        type=ReasonType(r["type"]),
                        polarity=Polarity(r["polarity"]),
                        contribution=float(r["contribution"]),
                        text=r["text"],
                    )
                    for r in item["reasons"]
                ),
                is_excluded=bool(item["is_excluded"]),
                exclusion_reason=item["exclusion_reason"],
                is_stretch=bool(item["is_stretch"]),
            )
        )
    return items, computed_at


async def _write_cache(
    user_id: uuid.UUID, results: list[MatchResult], computed_at: datetime
) -> None:
    try:
        await get_redis().setex(
            key_recommendations(user_id), REC_CACHE_TTL_SECONDS, _encode(results, computed_at)
        )
    except RedisError as exc:
        log.warning("rec_cache_write_failed", error=str(exc))


async def invalidate(user_id: uuid.UUID) -> None:
    """§8.12 — پس از تغییر نیمرخ، ثبت درخواست، یا بازخورد پیشنهاد."""
    try:
        await get_redis().delete(key_recommendations(user_id))
    except RedisError as exc:
        log.warning("rec_cache_invalidate_failed", user_id=str(user_id), error=str(exc))


__all__ = [
    "CANDIDATE_LIMIT",
    "PREVIEW_SIZE",
    "REC_CACHE_TTL_SECONDS",
    "candidate_query",
    "invalidate",
    "load_candidates",
    "load_student_context",
    "taxonomy_titles",
    "preview",
    "record_feedback",
    "rank",
    "recommend",
    "spec_for_project",
]
