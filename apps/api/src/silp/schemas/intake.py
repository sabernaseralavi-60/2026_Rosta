"""مدل‌های «طرح مسئله / نیاز» و «همکاری با ما» — ADR-0030، فایل مشخصات فاز ۰ بند ۲۰ و ۲۳."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from silp.domain.identity.normalize import normalize_email, normalize_mobile

NeedType = Literal["Commercial", "Research", "Education", "Consulting", "Collaboration", "Other"]
Service = Literal[
    "Website / Web App",
    "AI",
    "Data Analysis",
    "Automation",
    "Content",
    "Research",
    "Engineering",
    "GIS",
    "Consulting",
    "Training",
    "Other",
]
HasData = Literal["YES", "NO", "UNSURE"]
HoursPerWeek = Literal["LT2", "2_5", "5_10", "GT10"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]


class _Contact(BaseModel):
    """حداقل یک راه تماس لازم است؛ شماره و ایمیل نرمال می‌شوند."""

    name: Name
    mobile: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    organization: Short | None = None
    #: تله برای ربات: فیلد پنهانِ فرم که آدم خالی می‌گذارد.
    website: str = Field(default="", max_length=200)

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, value: object) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        mobile = normalize_mobile(str(value))
        if mobile is None:
            raise ValueError("شمارهٔ موبایل معتبر نیست.")
        return mobile

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: object) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        email = normalize_email(str(value))
        if email is None:
            raise ValueError("نشانی ایمیل معتبر نیست.")
        return email

    @model_validator(mode="after")
    def _contact_required(self) -> Self:
        if self.mobile is None and self.email is None:
            raise ValueError("شمارهٔ موبایل یا ایمیل لازم است.")
        return self


class IntakeIn(_Contact):
    need_type: NeedType
    services: Annotated[list[Service], Field(max_length=11)] = []
    summary: Body
    expected_result: Long | None = None
    sector: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    has_data: HasData | None = None
    timeline: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    budget: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    notes: Long | None = None


class CollaborationIn(_Contact):
    intro: Body
    specialty: Short | None = None
    skills: Annotated[str, StringConstraints(strip_whitespace=True, max_length=400)] | None = None
    experience: Long | None = None
    interests: Annotated[str, StringConstraints(strip_whitespace=True, max_length=400)] | None = (
        None
    )
    ways: Annotated[
        list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]],
        Field(max_length=12),
    ] = []
    hours_per_week: HoursPerWeek | None = None
    portfolio_url: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None

    @field_validator("portfolio_url", mode="before")
    @classmethod
    def _portfolio_is_https(cls, value: object) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        url = str(value).strip()
        if not url.startswith("https://"):
            raise ValueError("پیوند نمونه‌کار باید با https:// شروع شود.")
        return url


class SubmissionOut(BaseModel):
    tracking_code: str
    #: اگر شمارهٔ تماس با یک کاربر موجود یکی بود، کد شخصی همان فرد.
    person_code: str | None = None
    message: str
