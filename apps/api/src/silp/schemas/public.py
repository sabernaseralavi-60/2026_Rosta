"""مدل‌های عمومی — صفحهٔ اصلی، نیمرخ عمومی و گواهی. §5.3، §5.3.1، ADR-0017."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

CertificateKind = Literal["PROJECT", "COURSE", "RESEARCH_LEVEL"]


class PublicStatsOut(BaseModel):
    """§5.3.1 — «سرور عدد واقعی برمی‌گرداند و تصمیم نمایش با رابط است»."""

    students: int
    active_projects: int
    completed_projects: int
    completed_milestones: int
    research_outputs: int
    verified_revenue_rial: int
    active_courses: int
    certificates: int


class StoryMemberOut(BaseModel):
    name: str
    username: str
    is_lead: bool


class StoryOut(BaseModel):
    project_id: uuid.UUID
    title_fa: str
    summary: str
    kind: str
    kind_fa: str
    course_title: str | None
    completed_at: datetime | None
    team_size: int
    approved_milestones: int
    members: list[StoryMemberOut]


# ── گواهی ─────────────────────────────────────────────────────────────
class CertificateOut(BaseModel):
    """گواهی من — `GET /me/certificates`."""

    id: uuid.UUID
    public_code: str
    kind: CertificateKind
    kind_fa: str
    title_fa: str
    issued_at: datetime
    issuer_name: str
    verify_path: str
    details: dict[str, Any] = Field(default_factory=dict)
    revoked_at: datetime | None = None
    revoke_reason: str | None = None


class CertificateVerifyOut(BaseModel):
    """`GET /public/certificates/{code}`.

    `valid = false` با `revoked_at` یعنی گواهی صادر شده بود و باطل شد؛
    کدی که هرگز صادر نشده ۴۰۴ می‌گیرد (ADR-0017).
    """

    valid: bool
    public_code: str
    kind: CertificateKind
    kind_fa: str
    title_fa: str
    holder_name: str
    #: فقط اگر دارنده نیمرخش را عمومی کرده باشد.
    holder_username: str | None
    issued_at: datetime
    issuer: str
    details: dict[str, Any] = Field(default_factory=dict)
    revoked_at: datetime | None = None
    revoke_reason: str | None = None


class CertificateRevokeIn(BaseModel):
    reason: Annotated[str, Field(min_length=5, max_length=500)]


# ── نیمرخ عمومی ────────────────────────────────────────────────────────
class PublicSkillOut(BaseModel):
    title_fa: str
    level: int
    verified: bool


class PublicProjectOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    kind: str
    kind_fa: str
    role_fa: str
    completed_at: datetime | None


class PublicCertificateOut(BaseModel):
    public_code: str
    kind: CertificateKind
    title_fa: str
    issued_at: datetime


class PublicOutputOut(BaseModel):
    title: str
    kind_fa: str
    venue: str | None
    doi: str | None
    url: str | None


class PublicBadgeOut(BaseModel):
    code: str
    title_fa: str
    description: str
    icon: str
    tier: str
    awarded_at: datetime


class PublicLevelOut(BaseModel):
    total: int
    level: int
    title_fa: str


class PublicProfileOut(BaseModel):
    """FR-PROF-03 — بخش خاموش `null` یا خالی است، نه پنهان در رابط.

    هیچ فیلدی برای موبایل، ایمیل، کد ملی، نمره یا رتبهٔ کلاس وجود ندارد.
    """

    username: str
    name: str
    bio: str | None
    #: صاحب نیمرخ که پیش‌نمایش خودش را می‌بیند، حتی وقتی عمومی نیست.
    is_owner: bool
    is_public: bool
    sections: dict[str, bool]
    university: str | None = None
    field_of_study: str | None = None
    degree_level_fa: str | None = None
    skills: list[PublicSkillOut] = Field(default_factory=list)
    projects: list[PublicProjectOut] = Field(default_factory=list)
    certificates: list[PublicCertificateOut] = Field(default_factory=list)
    research_level: int | None = None
    research_level_fa: str | None = None
    research_outputs: list[PublicOutputOut] = Field(default_factory=list)
    badges: list[PublicBadgeOut] = Field(default_factory=list)
    points: PublicLevelOut | None = None
    member_since: datetime
