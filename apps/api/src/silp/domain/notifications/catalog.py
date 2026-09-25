"""فهرست انواع اعلان — PRD §4.9، §14.7، FR-MSG-01/02، M6.

هر اعلانی که سامانه می‌سازد، یکی از این انواع است. نوع چهار چیز را ثابت
می‌کند:

| ویژگی | کاربرد |
|-------|--------|
| `group` | دستهٔ ترجیحات کاربر (§4.9 `notification_preferences.kind_group`) |
| `priority` | اولویت پیش‌فرض؛ `URGENT` از ساعت آرام عبور می‌کند |
| `variables` | متغیرهای مجاز الگو — ویرایش الگو با متغیر ناشناخته رد می‌شود |
| `allow_sms` | پیامک هزینه دارد؛ اعلان کم‌ارزش هرگز پیامک نمی‌شود (ADR-0013) |

متن پیام اینجا نیست؛ در جدول `message_templates` است تا مدیر بدون
استقرار عوضش کند (FR-MSG-03). دادهٔ اولیه‌اش در مهاجرت ۰۰۱۳ است و تست
`test_seeded_templates_match_catalog` این دو را هم‌تراز نگه می‌دارد.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Group = Literal["COURSE", "PROJECT", "SOCIAL", "SYSTEM"]
Priority = Literal["LOW", "NORMAL", "IMPORTANT", "URGENT"]
Channel = Literal["IN_APP", "EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP"]

GROUPS: tuple[Group, ...] = ("COURSE", "PROJECT", "SOCIAL", "SYSTEM")
PRIORITIES: tuple[Priority, ...] = ("LOW", "NORMAL", "IMPORTANT", "URGENT")
#: کانال‌های جدول `outbox_messages` — §4.9. `IN_APP` در صف نمی‌رود.
EXTERNAL_CHANNELS: tuple[Channel, ...] = ("EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP")
CHANNELS: tuple[Channel, ...] = ("IN_APP", *EXTERNAL_CHANNELS)
#: کانال‌هایی که نشانی‌شان را کاربر با پیوند دادن حساب پیام‌رسان می‌سازد.
LINKABLE_CHANNELS: tuple[Channel, ...] = ("TELEGRAM", "EITAA")

GROUP_TITLE_FA: dict[Group, str] = {
    "COURSE": "دروس",
    "PROJECT": "پروژه‌ها",
    "SOCIAL": "نشان و جامعه",
    "SYSTEM": "حساب و سامانه",
}

GROUP_DESCRIPTION_FA: dict[Group, str] = {
    "COURSE": "هفتهٔ تازه، آزمون، نتیجه، اعلان‌های استاد و پاسخ به پرسش‌هایت",
    "PROJECT": "درخواست پیوستن، دعوت و آگهی تیم، تحویل‌دادنی، مهلت مرحله، کسب‌وکار و پژوهش",
    "SOCIAL": "نشان‌های تازه و ایده‌های تو",
    "SYSTEM": "امنیت حساب، خوش‌آمد و خلاصهٔ هفتگی",
}

CHANNEL_TITLE_FA: dict[Channel, str] = {
    "IN_APP": "داخل سامانه",
    "EMAIL": "ایمیل",
    "SMS": "پیامک",
    "TELEGRAM": "تلگرام",
    "EITAA": "ایتا",
    "WHATSAPP": "واتساپ",
}

PRIORITY_RANK: dict[Priority, int] = {"LOW": 0, "NORMAL": 1, "IMPORTANT": 2, "URGENT": 3}

#: کانال‌های پیش‌فرض هر دسته وقتی کاربر ترجیحی ثبت نکرده — ADR-0013.
#:
#: پیامک برای پروژه روشن است چون تعریف انجام‌شدهٔ M6 همین را می‌خواهد
#: («تأیید تحویل‌دادنی ⇒ اعلان داخلی + پیامک») و تعداد این پیام‌ها کم است.
#: برای درس خاموش است: «هفتهٔ تازه منتشر شد» هر هفته به همهٔ کلاس
#: می‌رود و پیامکش هم پرهزینه است و هم مزاحم.
DEFAULT_CHANNELS: dict[Group, tuple[Channel, ...]] = {
    "COURSE": ("IN_APP", "EMAIL"),
    "PROJECT": ("IN_APP", "SMS"),
    "SOCIAL": ("IN_APP",),
    "SYSTEM": ("IN_APP", "EMAIL", "SMS"),
}

#: متغیرهایی که هر الگو بدون اعلام هم دارد.
COMMON_VARIABLES: tuple[str, ...] = ("name", "link")


@dataclass(frozen=True, slots=True)
class Kind:
    code: str
    group: Group
    priority: Priority
    title_fa: str
    variables: tuple[str, ...] = ()
    allow_sms: bool = False

    @property
    def all_variables(self) -> tuple[str, ...]:
        return (*COMMON_VARIABLES, *self.variables)


_KINDS: tuple[Kind, ...] = (
    # ── دروس ───────────────────────────────────────────────────────────
    Kind(
        "ENROLLMENT_REQUESTED",
        "COURSE",
        "NORMAL",
        "درخواست ثبت‌نام تازه (استاد)",
        ("student", "course"),
    ),
    Kind(
        "ENROLLMENT_APPROVED",
        "COURSE",
        "NORMAL",
        "تأیید ثبت‌نام درس",
        ("course",),
        allow_sms=True,
    ),
    Kind("ENROLLMENT_REJECTED", "COURSE", "NORMAL", "رد ثبت‌نام درس", ("course",)),
    Kind("WEEK_PUBLISHED", "COURSE", "NORMAL", "انتشار هفتهٔ تازه", ("course", "week", "title")),
    Kind(
        "QUIZ_OPENED",
        "COURSE",
        "NORMAL",
        "باز شدن آزمون",
        ("course", "quiz", "closes_at"),
        allow_sms=True,
    ),
    Kind(
        "QUIZ_CLOSING",
        "COURSE",
        "IMPORTANT",
        "یادآوری مهلت آزمون",
        ("course", "quiz", "days", "closes_at"),
        allow_sms=True,
    ),
    Kind("QUIZ_RESULT", "COURSE", "NORMAL", "نتیجهٔ آزمون", ("quiz", "score", "total")),
    Kind("APPEAL_RESOLVED", "COURSE", "NORMAL", "پاسخ اعتراض به نمره", ("quiz", "outcome")),
    Kind(
        "ANNOUNCEMENT_POSTED",
        "COURSE",
        "NORMAL",
        "اعلان استاد",
        ("course", "title", "excerpt"),
        allow_sms=True,
    ),
    # ── پرسش‌وپاسخ درس — ADR-0024 ─────────────────────────────────────
    Kind(
        "QA_REPLY_POSTED",
        "COURSE",
        "NORMAL",
        "پاسخ تازه به پرسش تو",
        ("course", "thread", "replier", "excerpt"),
    ),
    Kind(
        "QA_REPLY_ENDORSED",
        "COURSE",
        "NORMAL",
        "تأیید استاد بر پاسخ تو",
        ("course", "thread", "reward"),
    ),
    # ── سپردن ارائه — ADR-0021 ────────────────────────────────────────
    Kind(
        "OFFERING_ASSIGNED",
        "COURSE",
        "IMPORTANT",
        "سپرده شدن ارائه به تو (استاد)",
        ("course", "term"),
    ),
    Kind(
        "OFFERING_REASSIGNED",
        "COURSE",
        "IMPORTANT",
        "سپرده شدن ارائه‌ات به استاد دیگر",
        ("course", "term", "instructor"),
    ),
    # ── پروژه‌ها ────────────────────────────────────────────────────────
    Kind(
        "APPLICATION_SUBMITTED",
        "PROJECT",
        "NORMAL",
        "درخواست پیوستن تازه (مدیر پروژه)",
        ("project", "applicant"),
    ),
    Kind(
        "APPLICATION_ACCEPTED",
        "PROJECT",
        "IMPORTANT",
        "پذیرش درخواست پیوستن",
        ("project",),
        allow_sms=True,
    ),
    Kind(
        "APPLICATION_REJECTED",
        "PROJECT",
        "NORMAL",
        "رد درخواست پیوستن",
        ("project", "reason"),
    ),
    Kind(
        "APPLICATION_WAITLISTED",
        "PROJECT",
        "NORMAL",
        "قرار گرفتن در فهرست انتظار",
        ("project",),
    ),
    Kind(
        "DELIVERABLE_SUBMITTED",
        "PROJECT",
        "NORMAL",
        "تحویل تازه برای بررسی (مدیر پروژه)",
        ("project", "milestone", "submitter"),
    ),
    Kind(
        "DELIVERABLE_APPROVED",
        "PROJECT",
        "IMPORTANT",
        "تأیید تحویل‌دادنی",
        ("project", "milestone", "points"),
        allow_sms=True,
    ),
    Kind(
        "DELIVERABLE_CHANGES",
        "PROJECT",
        "IMPORTANT",
        "درخواست اصلاح تحویل‌دادنی",
        ("project", "milestone", "feedback"),
        allow_sms=True,
    ),
    Kind(
        "DELIVERABLE_REJECTED",
        "PROJECT",
        "IMPORTANT",
        "رد تحویل‌دادنی",
        ("project", "milestone", "feedback"),
        allow_sms=True,
    ),
    Kind(
        "DEADLINE_REMINDER",
        "PROJECT",
        "IMPORTANT",
        "یادآوری مهلت مرحله",
        ("project", "milestone", "days", "due_on"),
        allow_sms=True,
    ),
    Kind(
        "PROJECT_STALLED",
        "PROJECT",
        "IMPORTANT",
        "بی‌تحرکی پروژه",
        ("project", "days"),
    ),
    Kind(
        "REFLECTION_REQUESTED",
        "PROJECT",
        "NORMAL",
        "درخواست بازتاب پایان پروژه",
        ("project", "reward"),
    ),
    # ── تیم و کارآفرینی (M7) ───────────────────────────────────────────
    Kind(
        "TEAM_INVITATION",
        "PROJECT",
        "IMPORTANT",
        "دعوت به تیم",
        ("inviter", "team", "message"),
        allow_sms=True,
    ),
    Kind(
        "INVITATION_ACCEPTED",
        "PROJECT",
        "NORMAL",
        "پذیرش دعوت (دعوت‌کننده)",
        ("invitee", "team"),
    ),
    Kind(
        "METRIC_REVIEWED",
        "PROJECT",
        "NORMAL",
        "نتیجهٔ بررسی فعالیت یا فروش",
        ("metric", "value", "owner", "decision", "detail"),
    ),
    Kind(
        "VENTURE_STAGE_CHANGED",
        "PROJECT",
        "NORMAL",
        "تغییر مرحلهٔ کسب‌وکار",
        ("venture", "stage", "from_stage"),
    ),
    # ── پژوهش و آگهی هم‌تیمی (M7 بخش ب) ───────────────────────────────
    Kind(
        "RESEARCH_SUBMITTED",
        "PROJECT",
        "NORMAL",
        "تحویل تازهٔ مسیر پژوهش (منتور)",
        ("student", "level"),
    ),
    Kind(
        "RESEARCH_REVIEWED",
        "PROJECT",
        "IMPORTANT",
        "نتیجهٔ بررسی سطح پژوهش",
        ("level", "decision", "detail"),
        allow_sms=True,
    ),
    Kind(
        "TOPIC_REVIEWED",
        "PROJECT",
        "NORMAL",
        "نتیجهٔ پیشنهاد موضوع پژوهشی",
        ("topic", "decision", "detail"),
    ),
    Kind(
        "TOPIC_RELEASE_WARNING",
        "PROJECT",
        "IMPORTANT",
        "هشدار آزاد شدن رزرو موضوع",
        ("topic", "days"),
    ),
    Kind("TOPIC_RELEASED", "PROJECT", "NORMAL", "آزاد شدن رزرو موضوع", ("topic", "days")),
    Kind(
        "OUTPUT_REVIEWED",
        "PROJECT",
        "NORMAL",
        "نتیجهٔ راستی‌آزمایی خروجی پژوهشی",
        ("title", "decision", "detail"),
    ),
    Kind(
        "OPENING_MATCH",
        "PROJECT",
        "LOW",
        "آگهی هم‌تیمی هم‌خوان با نیمرخ من",
        ("opening", "team", "skills"),
    ),
    Kind(
        "OPENING_APPLIED",
        "PROJECT",
        "NORMAL",
        "درخواست تازه برای آگهی (آگهی‌دهنده)",
        ("applicant", "opening"),
    ),
    Kind(
        "OPENING_DECIDED",
        "PROJECT",
        "IMPORTANT",
        "نتیجهٔ درخواست پیوستن از آگهی",
        ("opening", "team", "decision", "detail"),
        allow_sms=True,
    ),
    Kind("OPENING_EXPIRED", "PROJECT", "LOW", "پایان مهلت آگهی (آگهی‌دهنده)", ("opening",)),
    # ── آزمایشگاه شهر هوشمند (M7 بخش ج) ────────────────────────────────
    Kind(
        "MILESTONE_OWNER_ASSIGNED",
        "PROJECT",
        "NORMAL",
        "مسئول شدن یک مرحله",
        ("project", "milestone", "assigner"),
    ),
    Kind(
        "CITY_STAGE_UNLOCKED",
        "PROJECT",
        "NORMAL",
        "باز شدن مرحلهٔ بعد گردش‌کار شهری (مسئول مرحله)",
        ("project", "milestone", "number"),
    ),
    Kind(
        "CITY_WORKFLOW_COMPLETED",
        "PROJECT",
        "IMPORTANT",
        "کامل شدن گردش‌کار شهر هوشمند",
        ("project",),
    ),
    # ── نشان و جامعه ───────────────────────────────────────────────────
    Kind("BADGE_AWARDED", "SOCIAL", "LOW", "نشان تازه", ("badge",)),
    Kind("CERTIFICATE_ISSUED", "SOCIAL", "NORMAL", "صدور گواهی تازه", ("title",)),
    Kind(
        "IDEA_COMMENTED",
        "SOCIAL",
        "LOW",
        "نظر تازه روی ایدهٔ من",
        ("idea", "commenter", "excerpt"),
    ),
    Kind(
        "IDEA_PROMOTED",
        "SOCIAL",
        "IMPORTANT",
        "ارتقای ایدهٔ من",
        ("idea", "target", "title", "next_step"),
    ),
    # ── حساب و سامانه ──────────────────────────────────────────────────
    Kind("WELCOME", "SYSTEM", "LOW", "خوش‌آمد"),
    Kind(
        "SESSIONS_REVOKED",
        "SYSTEM",
        "URGENT",
        "بسته شدن نشست‌ها به دلیل فعالیت مشکوک",
        allow_sms=True,
    ),
    Kind("CHANNEL_LINKED", "SYSTEM", "NORMAL", "اتصال پیام‌رسان", ("channel",)),
    Kind(
        "WEEKLY_DIGEST",
        "SYSTEM",
        "LOW",
        "خلاصهٔ هفتگی دانشجو",
        ("points", "deadlines", "unread"),
    ),
    Kind(
        "WEEKLY_DIGEST_TEACHER",
        "SYSTEM",
        "LOW",
        "خلاصهٔ هفتگی استاد",
        ("reviews", "enrollments", "at_risk"),
    ),
    Kind("OUTBOX_DEAD", "SYSTEM", "IMPORTANT", "پیام‌های ارسال‌نشده (مدیر)", ("count",)),
    Kind(
        "CERTIFICATE_REVOKED",
        "SYSTEM",
        "IMPORTANT",
        "ابطال گواهی",
        ("title", "reason"),
    ),
    Kind("ROLE_GRANTED", "SYSTEM", "NORMAL", "نقش تازه در سامانه", ("role",)),
    Kind(
        "ACCOUNT_VIEWED_BY_SUPPORT",
        "SYSTEM",
        "IMPORTANT",
        "بررسی حساب به دست پشتیبانی",
        ("agent",),
    ),
    # ── اشتراک — ADR-0019 ──────────────────────────────────────────────
    Kind(
        "SUBSCRIPTION_ACTIVATED",
        "SYSTEM",
        "IMPORTANT",
        "فعال شدن اشتراک",
        ("plan", "ends_on"),
        allow_sms=True,
    ),
    Kind(
        "SUBSCRIPTION_REJECTED",
        "SYSTEM",
        "IMPORTANT",
        "تأیید نشدن درخواست اشتراک",
        ("plan", "reason"),
    ),
)

KINDS: dict[str, Kind] = {kind.code: kind for kind in _KINDS}

#: الگوهایی که اعلان نیستند و مستقیم در صف می‌روند — فعلاً فقط کد تأیید
#: پیام‌رسانی که پیوندش با کد انجام می‌شود (ایتا).
DIRECT_TEMPLATES: dict[str, tuple[str, ...]] = {"CHANNEL_VERIFY": ("code",)}


def kind(code: str) -> Kind:
    try:
        return KINDS[code]
    except KeyError:
        msg = f"نوع اعلان ناشناخته: {code}"
        raise ValueError(msg) from None


def template_variables(code: str) -> tuple[str, ...]:
    """متغیرهای مجاز یک الگو — نوع اعلان یا الگوی مستقیم."""
    if code in KINDS:
        return KINDS[code].all_variables
    if code in DIRECT_TEMPLATES:
        return DIRECT_TEMPLATES[code]
    msg = f"الگوی ناشناخته: {code}"
    raise ValueError(msg)


def normalize_channels(group: Group, channels: list[str] | tuple[str, ...]) -> tuple[Channel, ...]:
    """ترجیح کاربر به مجموعهٔ مرتب و معتبر — `IN_APP` همیشه هست.

    مرکز اعلان سابقهٔ همهٔ رویدادهاست؛ خاموش کردنش یعنی کاربر نمی‌فهمد
    چه چیزی را از دست داده. پس ترجیح فقط کانال‌های **بیرونی** را تعیین
    می‌کند.
    """
    wanted = set(channels) | {"IN_APP"}
    unknown = wanted - set(CHANNELS)
    if unknown:
        msg = f"کانال ناشناخته: {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    return tuple(c for c in CHANNELS if c in wanted)


def is_urgent(priority: Priority) -> bool:
    return priority == "URGENT"


__all__ = [
    "CHANNELS",
    "CHANNEL_TITLE_FA",
    "COMMON_VARIABLES",
    "DEFAULT_CHANNELS",
    "DIRECT_TEMPLATES",
    "EXTERNAL_CHANNELS",
    "GROUPS",
    "GROUP_DESCRIPTION_FA",
    "GROUP_TITLE_FA",
    "KINDS",
    "LINKABLE_CHANNELS",
    "PRIORITIES",
    "PRIORITY_RANK",
    "Channel",
    "Group",
    "Kind",
    "Priority",
    "is_urgent",
    "kind",
    "normalize_channels",
    "template_variables",
]
