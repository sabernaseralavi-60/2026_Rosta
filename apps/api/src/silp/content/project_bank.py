"""بانک پروژهٔ راه‌اندازی — §14.5، M7-16.

§13.3: «سامانه‌ای با ۳ پروژه، شکست‌خورده است.» این ۲۵ پروژه پیش از معرفی
در کلاس باید در بانک باشند. شش مورد اول همان نمونه‌های کامل §14.5‌اند؛
نوزده مورد بعد از سه منبع واقعی آمده‌اند، نه از خیال:

* کسب‌وکارهای جاری — خرمای صابر، نرم‌افزار مدیریت باغ، آهک؛
* دستورالعمل پروژهٔ پنج درس نیم‌سال ۱۴۰۴-۲ (ترابری، ترافیک پیشرفته،
  داده‌کاوی، روش تحقیق، پروژهٔ کارشناسی)؛
* موضوع‌هایی که دانشجویان همان نیم‌سال واقعاً روی دادهٔ واقعی کار کردند
  (تأخیر پرواز، تنگهٔ هرمز، STATS19، NGSIM). نام دانشجو هیچ‌جا نمی‌آید.

توزیع، قواعد «راهنمای نوشتن ۱۹ پروژهٔ باقی‌مانده» را برآورده می‌کند و
`tests/unit/test_project_bank.py` آن را می‌پاید؛ پوشش پنج پرسونا را
`python -m silp.scripts.check_coverage` می‌سنجد (ADR-0018).

جمع امتیاز مراحل هر پروژه با `rewards.points` برابر است — همان الگوی
P-01 در §14.5. پروژه‌ای با `workflow` مراحلش را از الگو می‌گیرد.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── ساختار ────────────────────────────────────────────────────────────────


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
class MilestoneSpec:
    title_fa: str
    description: str
    points: int
    output_kind: str
    checklist: tuple[str, ...] = ()


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
    milestones: tuple[MilestoneSpec, ...] = ()
    #: الگوی گردش‌کار (ADR-0016) — مراحل از الگو می‌آیند، نه از `milestones`.
    workflow: str | None = None


# ── دسته‌بندی مهارت‌ها برای قواعد توزیع §14.5 ─────────────────────────────
# «بدون نیاز به مهارت نرم‌افزاری» یعنی هیچ مهارت لازمی از دستهٔ `SOFTWARE`
# §14.1 نباشد.
SOFTWARE_SKILLS = frozenset(
    {
        "EXCEL",
        "PYTHON",
        "R",
        "GIS",
        "GRAPHIC_DESIGN",
        "AI_TOOLS",
        "SUMO",
        "AIMSUN",
        "AUTOCAD",
        "POWERBI",
        "WEB_DEV",
    }
)
VEHICLE_ASSETS = frozenset({"CAR", "PICKUP", "MOTORCYCLE"})


# ── بانک ──────────────────────────────────────────────────────────────────

PROJECTS: tuple[ProjectSeed, ...] = (
    # ═══ شش پروژهٔ مرجع §14.5 ════════════════════════════════════════════
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
        # §14.5 — مراحل و امتیازها عیناً از سند.
        milestones=(
            MilestoneSpec(
                "شناخت محصول و بازار",
                "چهار رقم، قیمت هر رقم، و سه گروه مشتری هدف با دلیل انتخاب. مهلت پیشنهادی ۷ روز.",
                20,
                "DOCUMENT",
                ("تفاوت چهار رقم در یک جدول آمده", "سه گروه مشتری با دلیل نام برده شده"),
            ),
            MilestoneSpec(
                "تولید بستهٔ محتوای بازاریابی",
                "عکس محصول، متن معرفی هر رقم، و یک برگهٔ قیمت قابل ارسال. مهلت پیشنهادی ۱۴ روز.",
                40,
                "MEDIA",
                ("هر رقم دست‌کم یک عکس واقعی دارد", "برگهٔ قیمت تاریخ دارد"),
            ),
            MilestoneSpec(
                "اولین ۱۰ تماس فروش",
                "فهرست ده تماس با نتیجهٔ هر کدام و آنچه از آن یاد گرفتی. مهلت پیشنهادی ۱۴ روز.",
                50,
                "DOCUMENT",
                ("هر تماس تاریخ و نتیجه دارد",),
            ),
            MilestoneSpec(
                "اولین فروش تأییدشده",
                "فروش در بخش «فعالیت و فروش» ثبت و به تأیید مدیر پروژه رسیده باشد."
                " مهلت پیشنهادی ۲۱ روز.",
                90,
                "SALES",
                ("شاخص فروش ثبت و تأیید شده",),
            ),
        ),
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
        workflow="CITY",
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
        milestones=(
            MilestoneSpec(
                "پروتکل جستجو",
                "پرسش پژوهش، پایگاه‌ها، رشتهٔ جستجو و معیار ورود و خروج — پیش از خواندن اولین مقاله.",
                60,
                "DOCUMENT",
                ("رشتهٔ جستجوی هر پایگاه عیناً آمده", "معیار ورود و خروج جدا نوشته شده"),
            ),
            MilestoneSpec(
                "غربالگری و نمودار PRISMA",
                "غربال عنوان و چکیده، سپس متن کامل؛ تعداد هر گام در نمودار PRISMA.",
                100,
                "DATA",
                ("عدد هر گام PRISMA با فهرست منابع می‌خواند",),
            ),
            MilestoneSpec(
                "ماتریس مرور ۶۰ منبع",
                "برای هر منبع: داده، روش، متغیرها، یافتهٔ اصلی و محدودیت.",
                140,
                "DATA",
                ("هر ردیف DOI دارد", "ستون روش برای همه پر است"),
            ),
            MilestoneSpec(
                "پیش‌نویس مرور ادبیات و شکاف پژوهشی",
                "متن مرور بر اساس ماتریس و یک پاراگراف صریح دربارهٔ شکاف.",
                100,
                "DOCUMENT",
                ("هر ادعا به منبعی در ماتریس ارجاع دارد",),
            ),
        ),
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
        milestones=(
            MilestoneSpec(
                "یادگیری نرم‌افزار و فهرست باغداران",
                "خودت همهٔ کارهای اصلی نرم‌افزار را انجام بده؛ فهرست بیست باغدار با راه تماس.",
                40,
                "DOCUMENT",
                ("هر کار اصلی نرم‌افزار یک بار انجام شده",),
            ),
            MilestoneSpec(
                "پنج نصب و آموزش حضوری",
                "نصب روی گوشی کشاورز و آموزش سه کار پرکاربرد؛ عکس یا گزارش هر بازدید.",
                120,
                "MEDIA",
                ("هر بازدید تاریخ و نام روستا دارد",),
            ),
            MilestoneSpec(
                "مشتری فعال پس از یک ماه",
                "کدام کشاورزها هنوز استفاده می‌کنند و چرا بقیه نه — با شاخص فعالیت ثبت‌شده.",
                140,
                "SALES",
                ("شاخص مشتری فعال ثبت و تأیید شده", "بازخورد مکتوب دست‌کم سه کاربر"),
            ),
        ),
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
        milestones=(
            MilestoneSpec(
                "واژه‌نامهٔ داده و پاک‌سازی",
                "هر ستون با معنا و واحد؛ هر ردیف حذف‌شده با دلیل. اسکریپت، نه ویرایش دستی.",
                110,
                "CODE",
                ("واژه‌نامه همهٔ ستون‌ها را پوشش می‌دهد", "پاک‌سازی از دادهٔ خام بازتولید می‌شود"),
            ),
            MilestoneSpec(
                "مدل پایه و مدل‌های درختی",
                "لوجیت ترتیبی به‌عنوان پایه، سپس جنگل تصادفی یا XGBoost با اعتبارسنجی درست.",
                170,
                "CODE",
                ("تقسیم آموزش و آزمون پیش از هر پیش‌پردازش", "بذر تصادفی ثابت است"),
            ),
            MilestoneSpec(
                "تفسیرپذیری",
                "SHAP یا اثر حاشیه‌ای؛ کدام عامل‌ها شدت را بالا می‌برند و به چه اندازه.",
                120,
                "DOCUMENT",
                ("هر ادعای علّی با احتیاط و دلیل نوشته شده",),
            ),
            MilestoneSpec(
                "پیش‌نویس مقاله و بستهٔ بازتولید",
                "متن مقاله و دفترچه‌ای که با یک اجرا همهٔ جدول‌ها و شکل‌ها را می‌سازد.",
                150,
                "MIXED",
                ("یک اجرای کامل از صفر همان اعداد مقاله را می‌دهد",),
            ),
        ),
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
        milestones=(
            MilestoneSpec(
                "فهرست سرنخ صنعتی",
                "سی کارخانهٔ مصرف‌کنندهٔ آهک در استان: صنعت، مصرف تقریبی، تأمین‌کنندهٔ فعلی.",
                60,
                "DATA",
                ("هر سرنخ راه تماس دارد", "منبع هر عدد مصرف نوشته شده"),
            ),
            MilestoneSpec(
                "تماس و جلسه",
                "دست‌کم ده تماس و دو جلسهٔ حضوری یا تلفنی با تصمیم‌گیرندهٔ خرید.",
                80,
                "DOCUMENT",
                ("نتیجهٔ هر تماس ثبت شده",),
            ),
            MilestoneSpec(
                "سفارش یا قرارداد",
                "اولین سفارش ثبت‌شده در «فعالیت و فروش» و تأییدشده.",
                110,
                "SALES",
                ("شاخص فروش تأیید شده",),
            ),
        ),
    ),
    # ═══ کارآفرینی — پنج پروژهٔ تازه ═══════════════════════════════════
    ProjectSeed(
        slug="p-07-saber-dates-online-store",
        title_fa="فروشگاه آنلاین و کانال محتوای خرمای صابر",
        summary="راه‌اندازی کانال فروش در پیام‌رسان‌های داخلی با عکس، ویدئو و سفارش آنلاین",
        description=(
            "پروژهٔ P-01 فروش را حضوری جلو می‌برد؛ این پروژه همان محصول را به گوشی"
            " مشتری می‌برد: کانال ایتا و روبیکا، عکاسی محصول، ویدئوی کوتاه، و مسیر"
            " سفارش ساده از پیام تا تحویل.\n\n"
            "کار از خانه انجام می‌شود و وسیلهٔ نقلیه لازم ندارد. دوربین کمک می‌کند، ولی"
            " عکاسی خوب با گوشی هم ممکن است. طراحی گرافیک را حین کار یاد می‌گیری."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=6,
        team_size_min=1,
        team_size_max=3,
        work_style="EITHER",
        expected_output="کانال فعال با تقویم محتوا + سفارش‌های آنلاین تأییدشده",
        rewards={"points": 200, "revenue_share_percent": 12},
        skills=(
            SkillSpec("GRAPHIC_DESIGN", 2, weight=2, teachable=True),
            SkillSpec("MARKETING_SKILL", 2, weight=2, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("CAMERA")),
        interests=("CONTENT", "MARKETING", "SALES"),
        roles=(RoleSpec("تولیدکنندهٔ محتوا", 2), RoleSpec("مسئول سفارش", 1)),
        tags=("خرما", "فروش آنلاین", "تولید محتوا"),
        milestones=(
            MilestoneSpec(
                "هویت کانال و تقویم محتوا",
                "نام، معرفی، و تقویم چهارهفته‌ای پست‌ها برای چهار رقم.",
                40,
                "DOCUMENT",
                ("تقویم برای هر هفته دست‌کم سه پست دارد",),
            ),
            MilestoneSpec(
                "عکاسی و ویدئوی محصول",
                "دست‌کم دوازده عکس و دو ویدئوی کوتاه از محصول واقعی.",
                60,
                "MEDIA",
                ("هر رقم در عکس‌ها دیده می‌شود",),
            ),
            MilestoneSpec(
                "مسیر سفارش و اولین فروش آنلاین",
                "از پیام مشتری تا تحویل؛ فروش در «فعالیت و فروش» ثبت و تأیید شده.",
                100,
                "SALES",
                ("مسیر سفارش مکتوب است", "شاخص فروش تأیید شده"),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-08-saber-dates-corporate-gifts",
        title_fa="فروش سازمانی بستهٔ هدیهٔ خرما",
        summary="فروش بستهٔ هدیهٔ خرما به شرکت‌ها و ادارات برای یلدا، نوروز و رمضان",
        description=(
            "شرکت‌ها هر سال برای کارکنان و مشتریانشان هدیهٔ مناسبتی می‌خرند و"
            " تصمیمش چند هفته پیش از مناسبت گرفته می‌شود. این پروژه همان پنجره را"
            " هدف می‌گیرد: فهرست سازمان‌ها، پیشنهاد مکتوب، و پیگیری تا سفارش.\n\n"
            "مهارت نرم‌افزاری لازم نیست؛ آنچه لازم است نامه‌نگاری مؤدبانه، ارائهٔ"
            " خوب و پیگیری است. با پنج ساعت در هفته هم پیش می‌رود."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=5,
        team_size_min=1,
        team_size_max=3,
        work_style="EITHER",
        expected_output="پیشنهاد فروش سازمانی + سفارش تأییدشده",
        rewards={"points": 220, "revenue_share_percent": 12},
        skills=(
            SkillSpec("PRESENTATION", 2, weight=2, teachable=True),
            SkillSpec("MARKETING_SKILL", 2, weight=2, teachable=True),
        ),
        assets=(AssetSpec("CAR"),),
        interests=("SALES", "COMMERCE", "MARKETING"),
        roles=(RoleSpec("کارشناس فروش سازمانی", 2), RoleSpec("مسئول پیگیری", 1)),
        tags=("خرما", "فروش سازمانی", "B2B"),
        milestones=(
            MilestoneSpec(
                "فهرست سازمان‌ها و مناسبت",
                "بیست سازمان هدف، مناسبت بعدی و مسئول خرید هر کدام.",
                40,
                "DATA",
                ("هر سازمان راه تماس با مسئول خرید دارد",),
            ),
            MilestoneSpec(
                "پیشنهاد مکتوب",
                "یک برگهٔ پیشنهاد با سه اندازهٔ بسته، قیمت و زمان تحویل.",
                60,
                "DOCUMENT",
                ("قیمت و زمان تحویل هر بسته آمده",),
            ),
            MilestoneSpec(
                "سفارش سازمانی",
                "دست‌کم یک سفارش سازمانی ثبت‌شده و تأییدشده.",
                120,
                "SALES",
                ("شاخص فروش تأیید شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-09-agri-software-video-guides",
        title_fa="آموزش ویدئویی نرم‌افزار مدیریت باغ",
        summary="ساخت ده ویدئوی کوتاه آموزشی برای کشاورزانی که نرم‌افزار را نصب کرده‌اند",
        description=(
            "پروژهٔ P-04 نشان داد کشاورز پس از آموزش حضوری هم چند هفته بعد"
            " فراموش می‌کند. ویدئوی کوتاه روی گوشی، همان جایی است که او دنبال"
            " جواب می‌گردد.\n\n"
            "ده ویدئوی یک تا دو دقیقه‌ای، هر کدام یک کار: ثبت آبیاری، ثبت سم‌پاشی،"
            " گزارش هزینه. نیازی به رفتن به باغ نیست و تک‌نفره هم ممکن است."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=5,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="ده ویدئوی آموزشی منتشرشده + آمار بازدید",
        rewards={"points": 180},
        skills=(
            SkillSpec("GRAPHIC_DESIGN", 2, weight=2, teachable=True),
            SkillSpec("PRESENTATION", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("CAMERA")),
        interests=("CONTENT", "AGRICULTURE", "GRAPHIC"),
        roles=(RoleSpec("سازندهٔ ویدئو", 1), RoleSpec("نویسندهٔ فیلم‌نامه", 1)),
        tags=("کشاورزی", "ویدئو", "آموزش مشتری"),
        milestones=(
            MilestoneSpec(
                "فهرست پرسش‌های پرتکرار",
                "ده کاری که کشاورزها بیشتر از همه می‌پرسند، از تیم پشتیبانی نرم‌افزار.",
                30,
                "DOCUMENT",
                (),
            ),
            MilestoneSpec(
                "پنج ویدئوی اول",
                "هر ویدئو زیر دو دقیقه، با زیرنویس فارسی.",
                70,
                "MEDIA",
                ("هر ویدئو زیر دو دقیقه است", "زیرنویس دارد"),
            ),
            MilestoneSpec(
                "پنج ویدئوی بعدی و بازخورد",
                "انتشار در کانال پشتیبانی و بازخورد دست‌کم سه کشاورز.",
                80,
                "MEDIA",
                ("بازخورد کشاورزها پیوست شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-10-lime-construction-dealers",
        title_fa="فروش آهک ساختمانی به مصالح‌فروشی‌ها",
        summary="ساختن شبکهٔ نمایندگی فروش آهک ساختمانی در مصالح‌فروشی‌های شهر",
        description=(
            "آهک صنعتی (P-06) مشتری کارخانه‌ای دارد؛ آهک ساختمانی از مصالح‌فروشی"
            " محله به بنا و پیمانکار می‌رسد. این پروژه همان زنجیره را می‌سازد:"
            " پیدا کردن مصالح‌فروشی‌ها، معرفی محصول و شرایط، و اولین سفارش.\n\n"
            "کار میدانی است ولی در شهر؛ وانت کمک می‌کند ولی لازم نیست — ارسال با"
            " کارخانه است."
        ),
        kind="A_VENTURE",
        difficulty=2,
        time_commitment_hpw=6,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="فهرست نمایندگی + سفارش تأییدشده",
        rewards={"points": 220, "revenue_share_percent": 10},
        skills=(
            SkillSpec("MARKETING_SKILL", 2, weight=3, teachable=True),
            SkillSpec("PRESENTATION", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("PICKUP"), AssetSpec("CAR")),
        interests=("SALES", "COMMERCE"),
        roles=(RoleSpec("کارشناس فروش میدانی", 2),),
        tags=("آهک", "مصالح ساختمانی", "فروش میدانی"),
        milestones=(
            MilestoneSpec(
                "نقشهٔ مصالح‌فروشی‌ها",
                "بیست مصالح‌فروشی با نشانی، تأمین‌کنندهٔ فعلی آهک و قیمت فروششان.",
                50,
                "DATA",
                ("نشانی و تلفن هر فروشگاه ثبت شده",),
            ),
            MilestoneSpec(
                "معرفی و شرایط همکاری",
                "بازدید از ده فروشگاه با برگهٔ شرایط؛ نتیجهٔ هر بازدید.",
                70,
                "DOCUMENT",
                ("نتیجهٔ هر بازدید ثبت شده",),
            ),
            MilestoneSpec(
                "اولین سفارش نماینده",
                "سفارش ثبت‌شده و تأییدشده.",
                100,
                "SALES",
                ("شاخص فروش تأیید شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-11-traffic-count-service",
        title_fa="خدمت شمارش ترافیک با ویدئو و هوش مصنوعی",
        summary="شمارش خودکار حجم و ترکیب ترافیک از ویدئو، به‌عنوان خدمت برای مشاوران ترافیک",
        description=(
            "مشاوران ترافیک هنوز برای شمارش تقاطع، آمارگیر سر چهارراه می‌فرستند."
            " این پروژه یک خدمت می‌سازد: فیلم‌برداری از تقاطع، شمارش خودکار با مدل"
            " تشخیص خودرو، و تحویل جدول استاندارد حجم به تفکیک جهت و نوع.\n\n"
            "خروجی باید با شمارش دستی یک ربع ساعت مقایسه شود — خدمتی که دقتش"
            " اثبات نشده، فروختنی نیست. سپس اولین سفارش از یک مشاور."
        ),
        kind="A_VENTURE",
        difficulty=4,
        time_commitment_hpw=10,
        team_size_min=2,
        team_size_max=4,
        work_style="TEAM",
        expected_output="خط لولهٔ شمارش با دقت سنجیده + سفارش از مشاور",
        rewards={"points": 400, "revenue_share_percent": 25},
        skills=(
            SkillSpec("PYTHON", 3, weight=3),
            SkillSpec("AI_TOOLS", 3, weight=2, teachable=True),
            SkillSpec("MARKETING_SKILL", 2, weight=1, teachable=True),
        ),
        assets=(
            AssetSpec("LAPTOP", mandatory=True),
            AssetSpec("CAMERA", mandatory=True),
            AssetSpec("POWERFUL_PC"),
        ),
        interests=("PROGRAMMING", "TRANSPORT", "COMMERCE"),
        roles=(RoleSpec("برنامه‌نویس بینایی ماشین", 2), RoleSpec("مسئول فروش خدمت", 1)),
        tags=("شمارش ترافیک", "بینایی ماشین", "خدمت"),
        milestones=(
            MilestoneSpec(
                "فیلم‌برداری و شمارش دستی مرجع",
                "یک ساعت فیلم از یک تقاطع و شمارش دستی یک ربع آن برای مقایسه.",
                60,
                "DATA",
                ("زاویهٔ دوربین همهٔ حرکت‌ها را می‌بیند",),
            ),
            MilestoneSpec(
                "شمارش خودکار و سنجش دقت",
                "تشخیص و ردیابی خودرو، شمارش هر حرکت، و خطای نسبی در برابر شمارش دستی.",
                180,
                "CODE",
                ("خطای هر حرکت گزارش شده", "کد با یک دستور اجرا می‌شود"),
            ),
            MilestoneSpec(
                "برگهٔ خدمت و اولین سفارش",
                "قیمت، زمان تحویل و نمونهٔ خروجی؛ اولین سفارش ثبت و تأییدشده.",
                160,
                "SALES",
                ("شاخص فروش تأیید شده",),
            ),
        ),
    ),
    # ═══ پژوهشی — چهار پروژهٔ تازه ═══════════════════════════════════════
    ProjectSeed(
        slug="p-12-flight-delay-weather",
        title_fa="پیش‌بینی تأخیر پرواز با دادهٔ عملکرد به‌موقع و آب‌وهوا",
        summary="ادغام دادهٔ عملکرد به‌موقع پروازها با دادهٔ هواشناسی و مدل‌سازی تأخیر",
        description=(
            "دادهٔ عملکرد به‌موقع پروازهای داخلی آمریکا (BTS) عمومی و مفصل است:"
            " هر پرواز با زمان برنامه، زمان واقعی و علت تأخیر. کار اصلی ادغام آن با"
            " دادهٔ هواشناسی فرودگاه است — جایی که بیشتر پروژه‌ها زمین می‌خورند.\n\n"
            "پرسش پژوهش باید مشخص باشد: کدام بخش تأخیر از آب‌وهواست و کدام از"
            " شبکهٔ پروازها. خروجی، گزارشی با قالب مقاله و کدی بازتولیدپذیر است."
        ),
        kind="B_RESEARCH",
        difficulty=3,
        time_commitment_hpw=8,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="مجموعه‌دادهٔ ادغام‌شده + مدل پیش‌بین + گزارش با قالب مقاله",
        rewards={"points": 350, "research_levels": [2]},
        skills=(
            SkillSpec("PYTHON", 3, weight=3),
            SkillSpec("STATISTICS", 3, weight=2),
            SkillSpec("ENGLISH", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("FAST_INTERNET", mandatory=True)),
        interests=("DATA_ANALYSIS", "TRANSPORT", "RESEARCH"),
        roles=(RoleSpec("تحلیلگر داده", 2),),
        tags=("حمل‌ونقل هوایی", "یادگیری ماشین", "دادهٔ باز"),
        milestones=(
            MilestoneSpec(
                "پرسش پژوهش و مرور",
                "پرسش دقیق، ده مقالهٔ نزدیک، و آنچه این کار اضافه می‌کند.",
                70,
                "DOCUMENT",
                ("پرسش قابل آزمون است",),
            ),
            MilestoneSpec(
                "ادغام پرواز و آب‌وهوا",
                "کلید ادغام (فرودگاه و ساعت)، نرخ ردیف‌های بی‌جفت و دلیلش.",
                110,
                "CODE",
                ("نرخ ردیف‌های بی‌جفت گزارش شده",),
            ),
            MilestoneSpec(
                "مدل و تفسیر",
                "مدل پایه در برابر مدل درختی؛ سهم آب‌وهوا در تأخیر.",
                170,
                "MIXED",
                ("اعتبارسنجی زمانی است، نه تصادفی",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-13-hormuz-shipping-disruption",
        title_fa="تحلیل اختلال ترافیک کشتیرانی تنگهٔ هرمز با دادهٔ AIS",
        summary="سنجش اثر رویدادهای ۲۰۲۶ بر تردد، سرعت و مسیر کشتی‌ها در تنگهٔ هرمز",
        description=(
            "تنگهٔ هرمز حساس‌ترین آبراه انرژی جهان است و دادهٔ AIS هر کشتی را"
            " چند بار در دقیقه ثبت می‌کند. پرسش ساده است و جواب سخت: رویدادهای"
            " امنیتی ۲۰۲۶ تردد، سرعت و مسیر کشتی‌ها را چقدر و تا کی تغییر دادند؟\n\n"
            "روش پیشنهادی مقایسهٔ پیش و پس از رویداد با گروه کنترل (مثلاً باب‌المندب)"
            " است. حجم داده بزرگ است؛ کامپیوتر قوی کمک می‌کند. GIS را حین کار یاد"
            " می‌گیری."
        ),
        kind="B_RESEARCH",
        difficulty=4,
        time_commitment_hpw=10,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="سری زمانی تردد و سرعت + برآورد اثر رویداد + پیش‌نویس مقاله",
        rewards={"points": 450, "research_levels": [2, 3]},
        skills=(
            SkillSpec("PYTHON", 3, weight=3),
            SkillSpec("STATISTICS", 3, weight=2),
            SkillSpec("GIS", 2, weight=1, teachable=True),
        ),
        assets=(
            AssetSpec("LAPTOP", mandatory=True),
            AssetSpec("FAST_INTERNET", mandatory=True),
            AssetSpec("POWERFUL_PC"),
        ),
        interests=("DATA_ANALYSIS", "TRANSPORT", "RESEARCH"),
        roles=(RoleSpec("تحلیلگر دادهٔ دریایی", 2),),
        tags=("حمل‌ونقل دریایی", "AIS", "تنگهٔ هرمز"),
        milestones=(
            MilestoneSpec(
                "دادهٔ AIS و پاک‌سازی",
                "محدودهٔ مکانی، بازهٔ زمانی، حذف پیام‌های نادرست و سفرهای تکراری.",
                120,
                "CODE",
                ("قواعد پاک‌سازی مکتوب و در کد است",),
            ),
            MilestoneSpec(
                "سری زمانی تردد و سرعت",
                "تردد روزانه و سرعت میانه به تفکیک نوع کشتی.",
                130,
                "DATA",
                ("نمودارها واحد و منبع دارند",),
            ),
            MilestoneSpec(
                "برآورد اثر رویداد",
                "مقایسه با گروه کنترل و آزمون فرض اصلی.",
                200,
                "MIXED",
                ("گروه کنترل و دلیل انتخابش آمده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-14-cyclist-injury-severity",
        title_fa="عوامل شدت آسیب دوچرخه‌سواران",
        summary="مدل شدت آسیب دوچرخه‌سواران با دادهٔ رسمی تصادفات بریتانیا ۲۰۲۱ تا ۲۰۲۴",
        description=(
            "دادهٔ STATS19 بریتانیا هر تصادف منجر به جرح را با جزئیات راه، زمان،"
            " آب‌وهوا و وسایل درگیر ثبت کرده است. دوچرخه‌سوار در این داده کم‌شمار"
            " ولی آسیب‌پذیر است؛ همین، پرسش پژوهشی خوبی می‌سازد.\n\n"
            "روش مرجع لوجیت ترتیبی یا پارامتر تصادفی است و R ابزار طبیعی آن."
            " پروژه به مسیر پژوهشی سطح ۲ و ۳ وصل است."
        ),
        kind="B_RESEARCH",
        difficulty=4,
        time_commitment_hpw=8,
        team_size_min=1,
        team_size_max=2,
        work_style="SOLO",
        expected_output="مدل شدت آسیب با تفسیر + پیش‌نویس مقاله",
        rewards={"points": 420, "research_levels": [2, 3]},
        skills=(
            SkillSpec("R", 3, weight=3),
            SkillSpec("STATISTICS", 3, weight=3),
            SkillSpec("WRITING", 3, weight=2),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("RESEARCH", "DATA_ANALYSIS", "TRANSPORT"),
        roles=(RoleSpec("پژوهشگر", 2),),
        tags=("ایمنی راه", "دوچرخه", "STATS19"),
        milestones=(
            MilestoneSpec(
                "پیشینهٔ پژوهش",
                "بیست مقاله دربارهٔ شدت آسیب دوچرخه‌سواران و متغیرهای پرتکرار.",
                90,
                "DOCUMENT",
                ("هر متغیر مدل در پیشینه پشتوانه دارد",),
            ),
            MilestoneSpec(
                "آماده‌سازی داده",
                "اتصال جدول‌های تصادف، وسیله و مصدوم؛ تعریف متغیر وابسته.",
                110,
                "CODE",
                ("واژه‌نامهٔ داده پیوست است",),
            ),
            MilestoneSpec(
                "مدل و اثر حاشیه‌ای",
                "لوجیت ترتیبی و یک مدل انعطاف‌پذیرتر؛ اثر حاشیه‌ای عوامل اصلی.",
                220,
                "MIXED",
                ("فرض خطوط موازی آزموده شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-15-ngsim-car-following",
        title_fa="کالیبراسیون مدل تعقیب خودرو با دادهٔ NGSIM",
        summary="کالیبراسیون مدل‌های IDM و Gipps با مسیرهای واقعی خودرو در بزرگراه I-80",
        description=(
            "دادهٔ NGSIM مسیر هر خودرو را هر یک‌دهم ثانیه دارد و پایهٔ ده‌ها مقالهٔ"
            " تعقیب خودرو است. کار این پروژه: استخراج جفت‌های پیشرو و پیرو، هموارسازی"
            " خطای اندازه‌گیری، و کالیبراسیون دو مدل با تابع هدف درست.\n\n"
            "دشوار است: هم ریاضیات مدل می‌خواهد هم برنامه‌نویسی دقیق. خروجی اگر"
            " خوب باشد، مستقیماً مقالهٔ کنفرانس است."
        ),
        kind="B_RESEARCH",
        difficulty=5,
        time_commitment_hpw=10,
        team_size_min=1,
        team_size_max=1,
        work_style="SOLO",
        expected_output="پارامترهای کالیبره با خطای اعتبارسنجی + مقالهٔ کنفرانس",
        rewards={"points": 480, "research_levels": [2, 3]},
        skills=(
            SkillSpec("R", 3, weight=2),
            SkillSpec("MODELING", 3, weight=3),
            SkillSpec("STATISTICS", 3, weight=2),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("POWERFUL_PC")),
        interests=("RESEARCH", "TRANSPORT", "PROGRAMMING"),
        roles=(RoleSpec("پژوهشگر", 1),),
        tags=("تعقیب خودرو", "NGSIM", "کالیبراسیون"),
        milestones=(
            MilestoneSpec(
                "استخراج و هموارسازی مسیرها",
                "جفت‌های پیشرو و پیرو بدون تغییر خط؛ هموارسازی سرعت و شتاب.",
                140,
                "CODE",
                ("روش هموارسازی و اثرش بر شتاب گزارش شده",),
            ),
            MilestoneSpec(
                "کالیبراسیون IDM و Gipps",
                "تابع هدف، الگوریتم بهینه‌سازی، و پارامترها برای هر جفت.",
                200,
                "CODE",
                ("تابع هدف با مرور ادبیات توجیه شده",),
            ),
            MilestoneSpec(
                "اعتبارسنجی و مقاله",
                "خطا روی جفت‌های کنارگذاشته و مقایسهٔ دو مدل؛ پیش‌نویس مقاله.",
                140,
                "DOCUMENT",
                ("داده‌های اعتبارسنجی در کالیبراسیون نبوده‌اند",),
            ),
        ),
    ),
    # ═══ حل مسئلهٔ واقعی — هفت پروژهٔ تازه ═══════════════════════════════
    ProjectSeed(
        slug="p-16-school-zone-safety-audit",
        title_fa="ممیزی ایمنی محدودهٔ مدارس کرمان",
        summary="بازدید میدانی و ممیزی ایمنی عابر در محدودهٔ یک مدرسه با چک‌لیست استاندارد",
        description=(
            "بیشتر مدارس شهر گذرگاه ایمن، تابلو یا کاهندهٔ سرعت کافی ندارند و"
            " کسی هم فهرستشان را ندارد. در این پروژه یک مدرسه را انتخاب می‌کنی، با"
            " چک‌لیست ممیزی ایمنی بازدید می‌کنی، عکس می‌گیری، و پیشنهاد کم‌هزینه"
            " می‌دهی.\n\n"
            "مهارت نرم‌افزاری لازم نیست و با چهار ساعت در هفته تمام می‌شود. خروجی"
            " همهٔ تیم‌ها کنار هم به معاونت ترافیک شهرداری داده می‌شود."
        ),
        kind="C_PROBLEM",
        difficulty=1,
        time_commitment_hpw=4,
        team_size_min=1,
        team_size_max=3,
        work_style="EITHER",
        expected_output="گزارش ممیزی با عکس و نقشه + سه پیشنهاد کم‌هزینه",
        rewards={"points": 150},
        skills=(
            SkillSpec("WRITING", 2, weight=1, teachable=True),
            SkillSpec("PRESENTATION", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("CAMERA"),),
        interests=("URBAN", "TRANSPORT", "RESEARCH"),
        roles=(RoleSpec("ممیز میدانی", 3),),
        tags=("ایمنی راه", "عابر پیاده", "مدرسه"),
        milestones=(
            MilestoneSpec(
                "انتخاب مدرسه و برنامهٔ بازدید",
                "مدرسه، محدودهٔ ۳۰۰ متری، و زمان بازدید در ساعت ورود و خروج دانش‌آموزان.",
                30,
                "DOCUMENT",
                (),
            ),
            MilestoneSpec(
                "بازدید و چک‌لیست",
                "چک‌لیست ممیزی کامل با عکس هر مورد ناایمن.",
                70,
                "MEDIA",
                ("هر مورد ناایمن عکس و موقعیت دارد",),
            ),
            MilestoneSpec(
                "گزارش و پیشنهاد",
                "سه پیشنهاد کم‌هزینه با اولویت و برآورد تقریبی هزینه.",
                50,
                "DOCUMENT",
                ("هر پیشنهاد به یک مورد ممیزی ارجاع دارد",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-17-signalized-intersection-los",
        title_fa="شمارش حجم و تحلیل ظرفیت یک تقاطع چراغ‌دار",
        summary="شمارش حجم ساعت اوج، زمان‌بندی چراغ و سطح سرویس یک تقاطع واقعی",
        description=(
            "همان فصل ظرفیت و سطح سرویس درس ترابری، روی یک تقاطع واقعی شهر:"
            " شمارش حجم ساعت اوج به تفکیک حرکت، ثبت زمان‌بندی چراغ، و محاسبهٔ"
            " تأخیر و سطح سرویس.\n\n"
            "پروژهٔ ورود آسان برای درس است؛ اکسل کافی است. پیشنهاد اصلاح زمان‌بندی"
            " و مقایسهٔ پیش و پس، آن را از تمرین کلاسی به یک توصیهٔ واقعی می‌رساند."
        ),
        kind="C_PROBLEM",
        difficulty=2,
        time_commitment_hpw=5,
        team_size_min=2,
        team_size_max=4,
        work_style="TEAM",
        expected_output="جدول حجم ساعت اوج + تحلیل سطح سرویس + پیشنهاد زمان‌بندی",
        rewards={"points": 200, "grade_weight": 15},
        skills=(
            SkillSpec("EXCEL", 2, weight=2),
            SkillSpec("MODELING", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("TRANSPORT", "URBAN", "DATA_ANALYSIS"),
        roles=(RoleSpec("آمارگیر", 2), RoleSpec("تحلیلگر ظرفیت", 2)),
        tags=("ظرفیت", "سطح سرویس", "تقاطع"),
        milestones=(
            MilestoneSpec(
                "شمارش ساعت اوج",
                "شمارش پانزده‌دقیقه‌ای یک ساعت اوج به تفکیک حرکت و نوع وسیله.",
                70,
                "DATA",
                ("ضریب ساعت اوج محاسبه شده",),
            ),
            MilestoneSpec(
                "زمان‌بندی و هندسه",
                "طول چرخه، فازها، زمان سبز و تعداد و عرض خطوط هر رویکرد.",
                40,
                "DATA",
                (),
            ),
            MilestoneSpec(
                "سطح سرویس و پیشنهاد",
                "تأخیر و سطح سرویس هر گروه خط، و زمان‌بندی پیشنهادی با مقایسه.",
                90,
                "DOCUMENT",
                ("روش محاسبه (HCM) نام برده شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-18-bus-stop-accessibility",
        title_fa="دسترس‌پذیری ایستگاه‌های اتوبوس برای افراد کم‌توان",
        summary="ممیزی میدانی دسترس‌پذیری ایستگاه‌های یک خط اتوبوس برای ویلچر، سالمند و نابینا",
        description=(
            "ایستگاه اتوبوسی که جدول بلند دارد یا پیاده‌رویش شکسته است، برای"
            " کاربر ویلچر عملاً وجود ندارد. این پروژه یک خط اتوبوس شهر را ایستگاه"
            " به ایستگاه با چک‌لیست دسترس‌پذیری بررسی می‌کند.\n\n"
            "تک‌نفره و با چهار ساعت در هفته ممکن است؛ هیچ نرم‌افزار خاصی لازم نیست."
            " گزارش نهایی به سازمان اتوبوسرانی داده می‌شود."
        ),
        kind="C_PROBLEM",
        difficulty=1,
        time_commitment_hpw=4,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="جدول ممیزی ایستگاه‌ها با عکس + فهرست اولویت اصلاح",
        rewards={"points": 150},
        skills=(SkillSpec("WRITING", 2, weight=1, teachable=True),),
        assets=(AssetSpec("CAMERA"),),
        interests=("URBAN", "TRANSPORT"),
        roles=(RoleSpec("ممیز میدانی", 2),),
        tags=("حمل‌ونقل همگانی", "دسترس‌پذیری", "اتوبوس"),
        milestones=(
            MilestoneSpec(
                "چک‌لیست و انتخاب خط",
                "چک‌لیست دسترس‌پذیری و فهرست ایستگاه‌های خط انتخابی.",
                30,
                "DOCUMENT",
                (),
            ),
            MilestoneSpec(
                "ممیزی ایستگاه‌ها",
                "هر ایستگاه با امتیاز چک‌لیست و عکس.",
                80,
                "MEDIA",
                ("هر ایستگاه دست‌کم یک عکس دارد",),
            ),
            MilestoneSpec(
                "اولویت اصلاح",
                "ایستگاه‌ها به ترتیب فوریت اصلاح، با دلیل.",
                40,
                "DOCUMENT",
                (),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-19-crash-hotspots-gis",
        title_fa="شناسایی نقاط پرتصادف محورهای برون‌شهری استان",
        summary="رتبه‌بندی نقاط پرتصادف با روش تجربی بیز و نمایش در GIS",
        description=(
            "شمردن تصادف‌ها نقطهٔ پرتصادف واقعی را نشان نمی‌دهد: محوری که حجم"
            " بیشتری دارد، طبیعتاً تصادف بیشتری هم دارد، و یک سال بد ممکن است"
            " اتفاقی باشد. روش تجربی بیز همین دو خطا را اصلاح می‌کند.\n\n"
            "این پروژه همان فصل درس ایمنی راه را روی دادهٔ واقعی استان اجرا"
            " می‌کند و خروجی‌اش فهرستی است که ادارهٔ راه می‌تواند بودجه‌اش را با آن"
            " اولویت‌بندی کند."
        ),
        kind="C_PROBLEM",
        difficulty=4,
        time_commitment_hpw=10,
        team_size_min=2,
        team_size_max=3,
        work_style="TEAM",
        expected_output="فهرست رتبه‌بندی‌شدهٔ نقاط پرتصادف + نقشه + گزارش",
        rewards={"points": 400, "grade_weight": 20},
        skills=(
            SkillSpec("GIS", 3, weight=3),
            SkillSpec("STATISTICS", 3, weight=3),
            SkillSpec("EXCEL", 3, weight=1),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("TRANSPORT", "DATA_ANALYSIS", "URBAN"),
        roles=(RoleSpec("تحلیلگر ایمنی", 2), RoleSpec("کارشناس GIS", 1)),
        tags=("ایمنی راه", "تجربی بیز", "GIS"),
        milestones=(
            MilestoneSpec(
                "قطعه‌بندی محور و اتصال داده",
                "قطعه‌های همگن، حجم ترافیک و تصادف هر قطعه در پنج سال.",
                120,
                "DATA",
                ("طول و حجم همهٔ قطعه‌ها معلوم است",),
            ),
            MilestoneSpec(
                "تابع عملکرد ایمنی و تجربی بیز",
                "مدل دوجمله‌ای منفی، پارامتر پراکندگی، و برآورد تجربی بیز هر قطعه.",
                170,
                "MIXED",
                ("برازش مدل گزارش شده",),
            ),
            MilestoneSpec(
                "نقشه و فهرست اولویت",
                "بیست قطعهٔ اول روی نقشه با مقایسهٔ رتبهٔ ساده و رتبهٔ تجربی بیز.",
                110,
                "DOCUMENT",
                ("تفاوت دو رتبه‌بندی توضیح داده شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-20-downtown-parking-study",
        title_fa="مطالعهٔ عرضه و تقاضای پارک مرکز شهر",
        summary="شمارش اشغال پارک در حاشیهٔ خیابان و پارکینگ‌های عمومی یک محدودهٔ تجاری",
        description=(
            "گلایهٔ همیشگی بازار مرکز شهر «جای پارک نیست» است، ولی کسی نمی‌داند"
            " چقدر نیست و کِی. این پروژه با شمارش ساعتی اشغال و نمونه‌گیری مدت توقف،"
            " تصویر واقعی را می‌سازد.\n\n"
            "کار میدانی است ولی پیاده؛ اکسل کافی است. خروجی به شهرداری منطقه"
            " تحویل می‌شود."
        ),
        kind="C_PROBLEM",
        difficulty=2,
        time_commitment_hpw=6,
        team_size_min=2,
        team_size_max=5,
        work_style="TEAM",
        expected_output="منحنی اشغال ساعتی + توزیع مدت توقف + پیشنهاد سیاست پارک",
        rewards={"points": 220, "grade_weight": 15},
        skills=(
            SkillSpec("EXCEL", 2, weight=2),
            SkillSpec("STATISTICS", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("URBAN", "TRANSPORT", "DATA_ANALYSIS"),
        roles=(RoleSpec("آمارگیر", 3), RoleSpec("تحلیلگر", 2)),
        tags=("پارک", "مرکز شهر", "آمارگیری"),
        milestones=(
            MilestoneSpec(
                "محدوده و ظرفیت",
                "نقشهٔ محدوده و ظرفیت هر قطعهٔ خیابان و پارکینگ.",
                40,
                "DATA",
                (),
            ),
            MilestoneSpec(
                "شمارش اشغال و مدت توقف",
                "شمارش ساعتی دو روز کاری و یک روز تعطیل؛ نمونهٔ مدت توقف با پلاک ناقص.",
                110,
                "DATA",
                ("هیچ پلاک کاملی ذخیره نشده",),
            ),
            MilestoneSpec(
                "تحلیل و پیشنهاد",
                "ساعت اوج اشغال، سهم توقف بلندمدت، و پیشنهاد سیاست.",
                70,
                "DOCUMENT",
                (),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-21-campus-od-mode-choice",
        title_fa="آمارگیری مبدأ-مقصد سفرهای دانشگاه و مدل انتخاب وسیله",
        summary="پرسش‌نامهٔ سفر دانشجویان و کارکنان، ماتریس مبدأ-مقصد و لوجیت انتخاب وسیله",
        description=(
            "همان فصل‌های تقاضای سفر درس برنامه‌ریزی حمل‌ونقل، روی جامعه‌ای که در"
            " دسترس است: دانشگاه. پرسش‌نامه، نمونه‌گیری، ماتریس مبدأ-مقصد به"
            " تفکیک ناحیه، و مدل لوجیت انتخاب وسیله.\n\n"
            "خروجی به معاونت دانشجویی برای برنامه‌ریزی سرویس داده می‌شود."
        ),
        kind="C_PROBLEM",
        difficulty=3,
        time_commitment_hpw=8,
        team_size_min=2,
        team_size_max=4,
        work_style="TEAM",
        expected_output="ماتریس مبدأ-مقصد + مدل انتخاب وسیله + گزارش برای دانشگاه",
        rewards={"points": 300, "grade_weight": 20},
        skills=(
            SkillSpec("STATISTICS", 2, weight=2),
            SkillSpec("EXCEL", 3, weight=2),
            SkillSpec("MODELING", 2, weight=2, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("TRANSPORT", "DATA_ANALYSIS", "URBAN"),
        roles=(RoleSpec("طراح پرسش‌نامه", 1), RoleSpec("مدل‌ساز تقاضا", 2)),
        tags=("تقاضای سفر", "مبدأ-مقصد", "لوجیت"),
        milestones=(
            MilestoneSpec(
                "پرسش‌نامه و نمونه‌گیری",
                "پرسش‌نامه، حجم نمونه و روش نمونه‌گیری با دلیل.",
                60,
                "DOCUMENT",
                ("حجم نمونه محاسبه شده، نه حدس زده شده",),
            ),
            MilestoneSpec(
                "گردآوری و ماتریس",
                "دست‌کم ۲۰۰ پاسخ پاک‌شده و ماتریس مبدأ-مقصد ناحیه‌ای.",
                120,
                "DATA",
                ("پاسخ‌های نامعتبر با دلیل کنار رفته‌اند",),
            ),
            MilestoneSpec(
                "مدل انتخاب وسیله",
                "لوجیت چندگانه با زمان و هزینهٔ سفر؛ ارزش زمان.",
                120,
                "MIXED",
                ("علامت ضرایب با انتظار نظری سنجیده شده",),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-22-municipal-traffic-dashboard",
        title_fa="داشبورد Power BI شاخص‌های ترافیک برای شهرداری",
        summary="داشبورد ماهانهٔ حجم، سرعت و تصادف محورهای اصلی از دادهٔ موجود شهرداری",
        description=(
            "شهرداری داده دارد — شمارش‌های دوره‌ای، دوربین‌های سرعت، گزارش"
            " تصادف — ولی هر کدام در یک فایل اکسل جدا. مدیر برای یک تصمیم ساده باید"
            " سه نفر را صدا کند.\n\n"
            "این پروژه یک داشبورد می‌سازد که هر ماه با جایگزین کردن فایل‌ها به‌روز"
            " می‌شود. Power BI را حین کار یاد می‌گیری؛ اکسل را باید بلد باشی."
        ),
        kind="C_PROBLEM",
        difficulty=3,
        time_commitment_hpw=6,
        team_size_min=1,
        team_size_max=2,
        work_style="EITHER",
        expected_output="داشبورد به‌روزشونده + راهنمای به‌روزرسانی ماهانه",
        rewards={"points": 280},
        skills=(
            SkillSpec("POWERBI", 3, weight=3, teachable=True),
            SkillSpec("EXCEL", 3, weight=2),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("DATA_ANALYSIS", "URBAN", "TRANSPORT"),
        roles=(RoleSpec("طراح داشبورد", 2),),
        tags=("داشبورد", "Power BI", "شهرداری"),
        milestones=(
            MilestoneSpec(
                "فهرست شاخص با مدیر",
                "ده شاخصی که مدیر هر ماه می‌پرسد، با منبع دادهٔ هر کدام.",
                50,
                "DOCUMENT",
                ("هر شاخص منبع داده دارد",),
            ),
            MilestoneSpec(
                "مدل داده و داشبورد",
                "جدول‌های پاک‌شده، رابطه‌ها و صفحه‌های داشبورد.",
                150,
                "MIXED",
                ("واحد و بازهٔ زمانی هر نمودار روشن است",),
            ),
            MilestoneSpec(
                "راهنمای به‌روزرسانی",
                "کارمندی که داشبورد را نساخته، با این راهنما ماه بعد را به‌روز کند.",
                80,
                "DOCUMENT",
                ("یک به‌روزرسانی آزمایشی با راهنما انجام شده",),
            ),
        ),
    ),
    # ═══ شخصی — سه پروژهٔ تازه ═══════════════════════════════════════════
    ProjectSeed(
        slug="p-23-sumo-self-study-portfolio",
        title_fa="خودآموز SUMO و ساخت نمونه‌کار",
        summary="یادگیری SUMO از صفر تا یک شبکهٔ کوچک واقعی، با نمونه‌کار قابل ارائه",
        description=(
            "برای کسی که SUMO را برای کار یا ادامهٔ تحصیل می‌خواهد و وقت کمی دارد:"
            " هفته‌ای چهار ساعت، با کتاب «مهندسی شبیه‌سازی ترافیک با SUMO» در"
            " کتابخانهٔ همین سامانه.\n\n"
            "مسیر از ساخت شبکه با netedit شروع می‌شود و به یک محدودهٔ کوچک واقعی از"
            " OSM با تقاضای ساده می‌رسد. خروجی، نمونه‌کاری است که در رزومه می‌نشیند."
        ),
        kind="D_PERSONAL",
        difficulty=2,
        time_commitment_hpw=4,
        team_size_min=1,
        team_size_max=1,
        work_style="SOLO",
        expected_output="شبکهٔ SUMO یک محدودهٔ واقعی + گزارش کوتاه نمونه‌کار",
        rewards={"points": 150},
        skills=(
            SkillSpec("SUMO", 2, weight=2, teachable=True),
            SkillSpec("PYTHON", 2, weight=1, teachable=True),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True),),
        interests=("TRANSPORT", "URBAN", "PROGRAMMING"),
        roles=(RoleSpec("یادگیرنده", 1),),
        tags=("SUMO", "خودآموز", "نمونه‌کار"),
        milestones=(
            MilestoneSpec(
                "شبکهٔ دست‌ساز",
                "یک تقاطع چهارراه با netedit و تقاضای ثابت؛ اجرا بدون خطا.",
                40,
                "CODE",
                (),
            ),
            MilestoneSpec(
                "شبکه از OSM",
                "یک محدودهٔ کوچک واقعی از OSM با netconvert و اصلاح خطاهای رایج.",
                60,
                "CODE",
                ("خطاهای اصلاح‌شده فهرست شده‌اند",),
            ),
            MilestoneSpec(
                "نمونه‌کار",
                "یک صفحه: چه ساختی، چه یاد گرفتی، و یک تصویر از شبیه‌سازی.",
                50,
                "DOCUMENT",
                (),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-24-english-abstract-clinic",
        title_fa="نوشتن چکیدهٔ انگلیسی مقاله با بازخورد",
        summary="نوشتن، بازنویسی و ویرایش چکیدهٔ انگلیسی یک پژوهش در سه دور بازخورد",
        description=(
            "بیشتر مقاله‌های دانشجویی پیش از داوری، در چکیده رد می‌شوند. این"
            " پروژه همان یک صفحه را جدی می‌گیرد: سه دور نوشتن و بازخورد، با"
            " الگوی ساختاریافتهٔ مجله‌های معتبر.\n\n"
            "هفته‌ای سه ساعت؛ مناسب کسی که مسیر پژوهشی را شروع کرده ولی نگارش"
            " انگلیسی‌اش را ضعیف می‌داند."
        ),
        kind="D_PERSONAL",
        difficulty=1,
        time_commitment_hpw=3,
        team_size_min=1,
        team_size_max=1,
        work_style="SOLO",
        expected_output="چکیدهٔ انگلیسی نهایی + تاریخچهٔ سه دور بازنویسی",
        rewards={"points": 100},
        skills=(
            SkillSpec("WRITING", 2, weight=2, teachable=True),
            SkillSpec("ENGLISH", 2, weight=2, teachable=True),
        ),
        assets=(),
        interests=("RESEARCH", "CONTENT"),
        roles=(RoleSpec("نویسنده", 1),),
        tags=("نگارش علمی", "انگلیسی", "مقاله"),
        milestones=(
            MilestoneSpec(
                "پیش‌نویس اول",
                "چکیدهٔ ساختاریافته: زمینه، هدف، روش، یافته، نتیجه — زیر ۲۵۰ واژه.",
                30,
                "DOCUMENT",
                ("زیر ۲۵۰ واژه است",),
            ),
            MilestoneSpec(
                "دو دور بازنویسی",
                "بازنویسی بر اساس بازخورد، با فهرست تغییرات هر دور.",
                50,
                "DOCUMENT",
                ("هر دور فهرست تغییرات دارد",),
            ),
            MilestoneSpec(
                "نسخهٔ نهایی",
                "چکیدهٔ نهایی و پنج کلیدواژه.",
                20,
                "DOCUMENT",
                (),
            ),
        ),
    ),
    ProjectSeed(
        slug="p-25-ai-assistants-for-engineering-data",
        title_fa="هوش مصنوعی به‌عنوان دستیار تحلیل دادهٔ مهندسی",
        summary="تحلیل یک مجموعه‌دادهٔ واقعی حمل‌ونقل با دستیار هوش مصنوعی و سنجش درستی خروجی‌اش",
        description=(
            "دستورالعمل درس‌های این نیم‌سال از دانشجو می‌خواهد با Claude و Google"
            " AI Studio کار کند — ولی دستیاری که کدش را نفهمی، دستیار نیست. در این"
            " پروژه یک مجموعه‌دادهٔ باز (مثلاً حجم ترافیک بین‌ایالتی) را با کمک"
            " دستیار تحلیل می‌کنی و هر ادعای آن را خودت می‌آزمایی.\n\n"
            "خروجی، گزارش کوتاهی است از آنچه دستیار درست گفت، آنچه اشتباه گفت، و"
            " چطور فهمیدی. هفته‌ای چهار ساعت کافی است."
        ),
        kind="D_PERSONAL",
        difficulty=1,
        time_commitment_hpw=4,
        team_size_min=1,
        team_size_max=1,
        work_style="SOLO",
        expected_output="تحلیل بازتولیدپذیر + گزارش خطاهای دستیار و روش کشفشان",
        rewards={"points": 120},
        skills=(
            SkillSpec("AI_TOOLS", 2, weight=2, teachable=True),
            SkillSpec("EXCEL", 2, weight=1),
        ),
        assets=(AssetSpec("LAPTOP", mandatory=True), AssetSpec("FAST_INTERNET")),
        interests=("DATA_ANALYSIS", "PROGRAMMING", "TRANSPORT"),
        roles=(RoleSpec("تحلیلگر", 1),),
        tags=("هوش مصنوعی", "تحلیل داده", "سواد داده"),
        milestones=(
            MilestoneSpec(
                "انتخاب داده و پرسش",
                "مجموعه‌داده، واژه‌نامه‌اش، و سه پرسشی که می‌خواهی جواب بدهی.",
                30,
                "DOCUMENT",
                (),
            ),
            MilestoneSpec(
                "تحلیل با دستیار",
                "گفت‌وگو با دستیار و کد یا فرمولی که از آن ساختی؛ اجرای دوباره روی داده.",
                50,
                "CODE",
                ("هر عدد گزارش با اجرای دوباره می‌خواند",),
            ),
            MilestoneSpec(
                "گزارش درستی",
                "کدام پاسخ دستیار درست بود، کدام نه، و چگونه فهمیدی.",
                40,
                "DOCUMENT",
                ("دست‌کم یک خطای دستیار مستند شده",),
            ),
        ),
    ),
)


__all__ = [
    "PROJECTS",
    "SOFTWARE_SKILLS",
    "VEHICLE_ASSETS",
    "AssetSpec",
    "MilestoneSpec",
    "ProjectSeed",
    "RoleSpec",
    "SkillSpec",
]
