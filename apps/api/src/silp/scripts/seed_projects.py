"""بانک پروژهٔ اولیه — §14.5.

شش پروژهٔ کاملاً مستندشدهٔ سند. این‌ها **دادهٔ واقعی‌اند**، نه Lorem Ipsum
(اصل ۶ §00): از کسب‌وکارها و پروژه‌های واقعی گرفته شده‌اند.

§14.5 برای **راه‌اندازی** (§13.3) حداقل ۲۵ پروژه می‌خواهد و الگوی نوشتن
۱۹ مورد باقی‌مانده را داده است. آن کار محتوایی است و به M7 تعلق دارد؛
M1 فقط به دادهٔ نامزد واقعی نیاز دارد تا موتور توصیه‌گر آزمایش شود.

اسکریپت بی‌اثر در تکرار است: کلید یکتایی `slug` است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.models.delivery import Milestone
from silp.models.identity import User
from silp.models.project import (
    Project,
    ProjectInterest,
    ProjectRequiredAsset,
    ProjectRequiredSkill,
    ProjectRole,
    Team,
    TeamMember,
)
from silp.models.taxonomy import Asset, Interest, Skill

log = get_logger("silp.seed.projects")

# M2 — هر پروژهٔ نمونه باید مرحله داشته باشد، وگرنه فضای کاری خالی
# است و جریان تحویل قابل امتحان نیست. الگو عمداً کوتاه و مشترک است؛
# مراحل واقعیِ هر پروژه در M7-16 با دادهٔ میدانی جایگزین می‌شوند.
MILESTONE_TEMPLATE: tuple[tuple[str, str, int, str], ...] = (
    ("شناخت و برنامه‌ریزی", "محدوده، ذی‌نفعان و برنامهٔ اجرا مشخص شود.", 20, "DOCUMENT"),
    ("اجرا", "کار اصلی پروژه انجام و شواهدش ثبت شود.", 50, "MIXED"),
    ("گزارش و تحویل نهایی", "خروجی نهایی تحویل و جمع‌بندی نوشته شود.", 30, "DOCUMENT"),
)


@dataclass(frozen=True, slots=True)
class SkillSpec:
    code: str
    min_level: int
    weight: int = 1
    teachable: bool = False


@dataclass(frozen=True, slots=True)
class AssetSpec:
    code: str
    mandatory: bool = False


@dataclass(frozen=True, slots=True)
class RoleSpec:
    title_fa: str
    slots: int = 1


@dataclass(frozen=True, slots=True)
class ProjectSeed:
    slug: str
    title_fa: str
    summary: str
    description: str
    kind: str
    difficulty: int
    time_commitment_hpw: int
    team_size_min: int
    team_size_max: int
    work_style: str
    expected_output: str
    rewards: dict[str, object]
    skills: tuple[SkillSpec, ...] = ()
    assets: tuple[AssetSpec, ...] = ()
    interests: tuple[str, ...] = ()
    roles: tuple[RoleSpec, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)


# §14.5 — شش پروژهٔ مرجع
PROJECTS: tuple[ProjectSeed, ...] = (
    ProjectSeed(
        slug="p-01-saber-dates",
        title_fa="فروش و بازاریابی خرمای صابر",
        summary=("فروش مستقیم چهار رقم خرمای مرغوب — مجول، پیارم، مضافتی و زاهدی — به مشتری نهایی"),
        description=(
            "خرمای صابر چهار رقم دارد و هر رقم بازار و مشتری خودش را می‌خواهد.\n\n"
            "کار دانشجو در این پروژه واقعی است و نتیجه‌اش قابل اندازه‌گیری: شناخت محصول،"
            " تولید محتوای بازاریابی، تماس با مشتری، و فروش تأییدشده. هیچ مرحله‌ای"
            " «تمرین» نیست — هر تماس با یک مشتری واقعی گرفته می‌شود.\n\n"
            "تیم بین بازاریابی، تولید محتوا و توزیع تقسیم می‌شود. اگر بازاریابی"
            " بلد نیستی، همین‌جا یاد می‌گیری؛ آنچه لازم است، پیگیری و صبر است."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=8,
        team_size_min=2,
        team_size_max=5,
        work_style="TEAM",
        expected_output="فروش تأییدشده + بستهٔ محتوای بازاریابی تولیدشده",
        rewards={"points": 200, "revenue_share_percent": 15},
        skills=(
            SkillSpec("MARKETING_SKILL", 2, weight=2, teachable=True),
            SkillSpec("GRAPHIC_DESIGN", 2, weight=1, teachable=True),
        ),
        assets=(
            AssetSpec("LAPTOP", mandatory=True),
            AssetSpec("MOTORCYCLE"),
            AssetSpec("CAR"),
        ),
        interests=("SALES", "MARKETING", "COMMERCE"),
        roles=(
            RoleSpec("بازاریاب", 2),
            RoleSpec("تولیدکنندهٔ محتوا", 1),
            RoleSpec("مسئول توزیع", 2),
        ),
        tags=("خرما", "فروش", "کشاورزی"),
    ),
    ProjectSeed(
        slug="p-02-sumo-kerman-corridor",
        title_fa="مدل‌سازی SUMO محور اصلی شهر کرمان",
        summary="ساخت مدل ریزنگر ترافیکی یک محور اصلی و ارائهٔ سناریوهای بهبود به شهرداری",
        description=(
            "این پروژه نمونهٔ کامل گردش‌کار هشت‌مرحله‌ای آزمایشگاه شهر هوشمند (§7.9) است:"
            " انتخاب محدوده، استخراج OSM، راستی‌آزمایی میدانی، مدل SUMO، تخمین تقاضا،"
            " سناریوسازی، گزارش مدیریتی، و داشبورد شهرداری.\n\n"
            "خروجی به شهرداری تحویل داده می‌شود، پس کیفیت داده و مستندسازی به‌اندازهٔ"
            " خود مدل اهمیت دارد. SUMO و GIS را می‌توانی همین‌جا یاد بگیری؛"
            " پایتون را باید از قبل بلد باشی."
        ),
        kind="C_PROBLEM",
        difficulty=4,
        time_commitment_hpw=12,
        team_size_min=3,
        team_size_max=5,
        work_style="TEAM",
        expected_output="مدل معتبر SUMO + گزارش مدیریتی + داشبورد",
        rewards={"points": 500, "grade_weight": 20, "certificate": True},
        skills=(
            SkillSpec("SUMO", 2, weight=3, teachable=True),
            SkillSpec("PYTHON", 3, weight=2),
            SkillSpec("GIS", 2, weight=2, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("FAST_INTERNET")),
        interests=("TRANSPORT", "URBAN", "PROGRAMMING"),
        roles=(
            RoleSpec("مدل‌ساز ترافیک", 2),
            RoleSpec("کارشناس داده و GIS", 1),
            RoleSpec("تحلیلگر سناریو", 2),
        ),
        tags=("SUMO", "ترافیک", "شهر هوشمند", "کرمان"),
    ),
    ProjectSeed(
        slug="p-03-crash-severity-review",
        title_fa="مرور نظام‌مند عوامل مؤثر بر شدت تصادفات",
        summary="مرور نظام‌مند مقالات ۲۰۱۵ تا ۲۰۲۵ و شناسایی شکاف پژوهشی برای مقالهٔ Q1",
        description=(
            "مرور نظام‌مند، کار پرحجم ولی روشنی است: پروتکل جستجو، غربالگری، استخراج"
            " داده از ۶۰ منبع، و ساخت ماتریس مرور.\n\n"
            "خروجی این پروژه مستقیماً بخش مرور ادبیات یک مقالهٔ Q1 می‌شود و مسیر"
            " پژوهشی سطح ۱ و ۲ را کامل می‌کند. مهارت آماری را می‌توانی حین کار"
            " بالا ببری، ولی انگلیسی و نگارش علمی پیش‌نیاز واقعی‌اند."
        ),
        kind="B_RESEARCH",
        difficulty=4,
        time_commitment_hpw=10,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="ماتریس مرور ۶۰ منبع + پیش‌نویس بخش مرور ادبیات",
        rewards={"points": 400, "research_levels": [1, 2]},
        skills=(
            SkillSpec("WRITING", 3, weight=3),
            SkillSpec("ENGLISH", 3, weight=3),
            SkillSpec("STATISTICS", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("FAST_INTERNET", mandatory=True)),
        interests=("RESEARCH", "TRANSPORT", "DATA_ANALYSIS"),
        roles=(RoleSpec("پژوهشگر اصلی", 1), RoleSpec("غربالگر منابع", 1)),
        tags=("مرور نظام‌مند", "ایمنی راه", "Q1"),
    ),
    ProjectSeed(
        slug="p-04-agri-software-rollout",
        title_fa="استقرار و آموزش نرم‌افزار مدیریت کشاورزی",
        summary="معرفی، نصب و آموزش نرم‌افزار مدیریت باغ به کشاورزان منطقه",
        description=(
            "نرم‌افزار آماده است؛ آنچه نیست، کشاورزی است که از آن استفاده کند.\n\n"
            "کار دانشجو رفتن به باغ، نشان دادن نرم‌افزار، نصب روی گوشی کشاورز،"
            " و آموزش چند کار ساده است. سخت‌ترین بخش، جلب اعتماد است، نه فناوری."
            " به همین دلیل مهارت ارائه و گفتگو مهم‌تر از مهارت نرم‌افزاری است.\n\n"
            "داشتن وسیلهٔ نقلیه الزامی است: باغ‌ها بیرون شهرند."
        ),
        kind="A_VENTURE",
        difficulty=3,
        time_commitment_hpw=10,
        team_size_min=2,
        team_size_max=4,
        work_style="TEAM",
        expected_output="تعداد مشتری فعال + بازخورد مکتوب کاربران",
        rewards={"points": 300, "revenue_share_percent": 20},
        skills=(
            SkillSpec("PRESENTATION", 3, weight=2),
            SkillSpec("MARKETING_SKILL", 2, weight=2, teachable=True),
        ),
        assets=(
            AssetSpec("LAPTOP", mandatory=True),
            AssetSpec("CAR", mandatory=True),
            AssetSpec("MOTORCYCLE"),
        ),
        interests=("AGRICULTURE", "SALES", "COMMERCE"),
        roles=(RoleSpec("مسئول استقرار", 2), RoleSpec("مربی کاربر", 2)),
        tags=("کشاورزی", "نرم‌افزار", "آموزش مشتری"),
    ),
    ProjectSeed(
        slug="p-05-crash-ml-analysis",
        title_fa="تحلیل داده‌های تصادفات استان با یادگیری ماشین",
        summary="مدل‌سازی پیش‌بین شدت تصادف با داده‌های پنج‌سالهٔ استان",
        description=(
            "دادهٔ خام پنج‌سالهٔ تصادفات استان در دسترس است. کار، تمیزکاری،"
            " مهندسی ویژگی، مدل‌سازی و تفسیر است.\n\n"
            "تأکید پروژه بر **بازتولیدپذیری** است: هر عددی که در مقاله می‌آید باید"
            " با اجرای دوبارهٔ دفترچه، دقیقاً همان عدد را بدهد. این سخت‌گیری،"
            " تفاوت یک پروژهٔ کلاسی با یک کار قابل انتشار است.\n\n"
            "این دشوارترین پروژهٔ فعلی بانک است. اگر پایتون و آمارت قوی نیست،"
            " اول پروژهٔ سبک‌تری بردار."
        ),
        kind="B_RESEARCH",
        difficulty=5,
        time_commitment_hpw=12,
        team_size_min=2,
        team_size_max=3,
        work_style="TEAM",
        expected_output="دفترچهٔ تحلیل بازتولیدپذیر + پیش‌نویس مقاله",
        rewards={"points": 550, "research_levels": [2, 3]},
        skills=(
            SkillSpec("PYTHON", 4, weight=3),
            SkillSpec("STATISTICS", 3, weight=3),
            SkillSpec("R", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("POWERFUL_PC")),
        interests=("DATA_ANALYSIS", "RESEARCH", "PROGRAMMING"),
        roles=(RoleSpec("مدل‌ساز", 2), RoleSpec("مسئول دادهٔ خام", 1)),
        tags=("یادگیری ماشین", "ایمنی راه", "دادهٔ واقعی"),
    ),
    ProjectSeed(
        slug="p-06-industrial-lime-market",
        title_fa="توسعهٔ بازار آهک صنعتی",
        summary="شناسایی مشتریان صنعتی جدید و توسعهٔ کانال فروش آهک",
        description=(
            "آهک صنعتی مشتری‌اش کارخانه است، نه مصرف‌کنندهٔ خانگی. یعنی فروش"
            " تلفنی و حضوری، نه تبلیغات اینستاگرامی.\n\n"
            "کار با ساختن فهرست سرنخ شروع می‌شود: چه کارخانه‌هایی در استان آهک"
            " مصرف می‌کنند، از کجا می‌خرند، و چرا ممکن است تأمین‌کننده عوض کنند."
            " سپس تماس، مذاکره، و در نهایت سفارش.\n\n"
            "پروژهٔ سبکی است (۶ ساعت در هفته) و تک‌نفره هم می‌شود انجامش داد —"
            " مناسب برای شروع."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=6,
        team_size_min=1,
        team_size_max=3,
        work_style="EITHER",
        expected_output="فهرست سرنخ واجد شرایط + قرارداد یا سفارش",
        rewards={"points": 250, "revenue_share_percent": 12},
        skills=(
            SkillSpec("MARKETING_SKILL", 2, weight=3, teachable=True),
            SkillSpec("EXCEL", 2, weight=1),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("SALES", "COMMERCE", "MARKETING"),
        roles=(RoleSpec("توسعه‌دهندهٔ بازار", 2), RoleSpec("تحلیلگر سرنخ", 1)),
        tags=("آهک", "فروش صنعتی", "B2B"),
    ),
)


async def _code_map(
    session: AsyncSession, model: type[Skill] | type[Asset] | type[Interest]
) -> dict[str, uuid.UUID]:
    """نگاشت کد ← شناسه. داده‌های اولیه با کد نوشته شده‌اند، نه UUID:
    UUIDها در هر محیط فرق می‌کنند و در سند §14 جایی ندارند."""
    rows = (await session.execute(select(model.code, model.id))).all()
    return {row.code: row.id for row in rows}


async def seed_projects(session: AsyncSession, lead_id: uuid.UUID) -> tuple[int, int]:
    """درج پروژه‌های §14.5. خروجی: (ساخته‌شده، از قبل موجود)."""
    skills = await _code_map(session, Skill)
    assets = await _code_map(session, Asset)
    interests = await _code_map(session, Interest)

    created = 0
    existing = 0

    for seed in PROJECTS:
        found = await session.scalar(select(Project).where(Project.slug == seed.slug))
        if found is not None:
            existing += 1
            continue

        project = Project(
            slug=seed.slug,
            title_fa=seed.title_fa,
            summary=seed.summary,
            description=seed.description,
            kind=seed.kind,
            # پروژهٔ نمونه باید بلافاصله در پیشنهادها دیده شود.
            status="OPEN",
            lead_id=lead_id,
            time_commitment_hpw=seed.time_commitment_hpw,
            team_size_min=seed.team_size_min,
            team_size_max=seed.team_size_max,
            work_style=seed.work_style,
            difficulty=seed.difficulty,
            expected_output=seed.expected_output,
            rewards=seed.rewards,
            tags=list(seed.tags),
        )
        session.add(project)
        await session.flush()

        for skill in seed.skills:
            if skill.code not in skills:
                log.warning("seed_unknown_skill", code=skill.code, project=seed.slug)
                continue
            session.add(
                ProjectRequiredSkill(
                    project_id=project.id,
                    skill_id=skills[skill.code],
                    min_level=skill.min_level,
                    weight=skill.weight,
                    is_teachable=skill.teachable,
                )
            )

        for asset in seed.assets:
            if asset.code not in assets:
                log.warning("seed_unknown_asset", code=asset.code, project=seed.slug)
                continue
            session.add(
                ProjectRequiredAsset(
                    project_id=project.id,
                    asset_id=assets[asset.code],
                    is_mandatory=asset.mandatory,
                )
            )

        for code in seed.interests:
            if code not in interests:
                log.warning("seed_unknown_interest", code=code, project=seed.slug)
                continue
            session.add(ProjectInterest(project_id=project.id, interest_id=interests[code]))

        for role in seed.roles:
            session.add(
                ProjectRole(project_id=project.id, title_fa=role.title_fa, slots=role.slots)
            )

        # §7.12 — پروژهٔ `OPEN` تیم دارد و مدیرش عضو `is_lead` آن است؛
        # همان کاری که `publish` می‌کند، اینجا دستی انجام می‌شود چون
        # پروژهٔ نمونه مستقیم `OPEN` ساخته می‌شود.
        team = Team(project_id=project.id, name=f"تیم {seed.title_fa}")
        session.add(team)
        await session.flush()
        session.add(TeamMember(team_id=team.id, user_id=lead_id, is_lead=True, status="ACTIVE"))

        for order, (title, description, points, output_kind) in enumerate(
            MILESTONE_TEMPLATE, start=1
        ):
            session.add(
                Milestone(
                    project_id=project.id,
                    title_fa=title,
                    description=description,
                    sort_order=order,
                    points=Decimal(points),
                    output_kind=output_kind,
                    checklist=[],
                )
            )

        created += 1
        log.info("seed_project_created", slug=seed.slug, kind=seed.kind)

    return created, existing


async def ensure_lead(session: AsyncSession, mobile: str) -> uuid.UUID:
    """مدیر پروژه‌های نمونه — حساب استاد §14.8."""
    user = await session.scalar(select(User).where(User.mobile == mobile))
    if user is None:
        stmt = insert(User).values(mobile=mobile).on_conflict_do_nothing().returning(User.id)
        created_id = await session.scalar(stmt)
        if created_id is not None:
            return created_id
        user = await session.scalar(select(User).where(User.mobile == mobile))
    if user is None:  # pragma: no cover — درج و خواندن هر دو شکست خورده
        msg = f"حساب مدیر پروژه ({mobile}) ساخته نشد."
        raise RuntimeError(msg)
    return user.id


__all__ = ["PROJECTS", "ProjectSeed", "ensure_lead", "seed_projects"]
