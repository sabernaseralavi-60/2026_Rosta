"""آینهٔ دادهٔ سایت در Vault — ADR-0030.

جهت: **سایت ← Vault، فقط‌خواندنی.** هر یادداشتِ ساخته‌شده `generated: true` دارد و
با اجرای بعدی بازنویسی می‌شود؛ ویرایش دستی آن‌ها به سایت برنمی‌گردد.

حریم خصوصی: Vault محلی است، ولی کد ملی (رمزشده در دیتابیس) **هرگز** صادر نمی‌شود.

افزودن یک آینهٔ تازه = نوشتن یک تابع `async def (session) -> list[Mirror]` و ثبتش
در `EXPORTERS`؛ بقیهٔ سیستم دست نمی‌خورد (ماژولار).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.permissions import Role
from silp.models.content import ContentItem
from silp.models.education import Course, CourseOffering, Enrollment, Term
from silp.models.identity import User, UserRole
from silp.models.intake import IntakeRequest
from silp.models.profile import Profile
from silp.models.project import Project

NEWLINE = chr(10)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class Mirror:
    """یک یادداشت آینه: پوشه، نام فایل، سرآیند و متن."""

    folder: str
    name: str
    meta: dict[str, Any]
    body: str = ""


@dataclass(slots=True)
class ExportReport:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def safe_name(text: str) -> str:
    cleaned = _UNSAFE.sub(" ", text).strip().rstrip(".")
    return re.sub(r"\s+", " ", cleaned)[:120] or "بی‌نام"


def render(mirror: Mirror) -> str:
    meta = {"generated": True, **mirror.meta}
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{head}---\n\n{mirror.body.strip()}\n"


def write_mirrors(vault: Path, mirrors: list[Mirror]) -> ExportReport:
    report = ExportReport()
    used: set[Path] = set()
    for mirror in mirrors:
        target = vault / mirror.folder / f"{safe_name(mirror.name)}.md"
        # دو یادداشت هم‌نام یکدیگر را بازنویسی می‌کردند و هر اجرا «تغییر» می‌دید.
        suffix = 2
        while target in used:
            target = vault / mirror.folder / f"{safe_name(mirror.name)} {suffix}.md"
            suffix += 1
        used.add(target)
        text = render(mirror)
        relative = target.relative_to(vault).as_posix()
        if target.is_file() and target.read_text(encoding="utf-8") == text:
            report.unchanged.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        report.written.append(relative)
    return report


# ── آینه‌ها ────────────────────────────────────────────────────────────
async def students(session: AsyncSession) -> list[Mirror]:
    rows = (
        await session.execute(
            select(User, Profile)
            .join(UserRole, UserRole.user_id == User.id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(UserRole.role_code == Role.STUDENT.value, User.deleted_at.is_(None))
            .distinct()
            .order_by(User.created_at)
        )
    ).all()
    enrollments = await _enrollments_by_student(session)
    out: list[Mirror] = []
    for user, profile in rows:
        name = (
            f"{profile.first_name} {profile.last_name}" if profile else (user.username or "بی‌نام")
        )
        taken = enrollments.get(user.id, [])
        out.append(
            Mirror(
                folder="02_Students",
                name=f"{name} ({user.person_code})",
                meta={
                    "type": "student",
                    "person_code": user.person_code,
                    "user_id": str(user.id),
                    "username": user.username,
                    "mobile": user.mobile,
                    "email": user.email,
                    "status": user.status,
                    "field_of_study": profile.field_of_study if profile else None,
                    "degree_level": profile.degree_level if profile else None,
                    "student_number": profile.student_number if profile else None,
                    "joined": user.created_at.date().isoformat(),
                    "courses": [t["course"] for t in taken],
                },
                body="# "
                + name
                + "\n\n## دروس\n"
                + (
                    "\n".join(f"- {t['course']} — {t['term']} ({t['status']})" for t in taken)
                    or "—"
                ),
            )
        )
    return out


async def _enrollments_by_student(session: AsyncSession) -> dict[Any, list[dict[str, str]]]:
    rows = (
        await session.execute(
            select(Enrollment.student_id, Course.title_fa, Term.title_fa, Enrollment.status)
            .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .order_by(Term.starts_on.desc())
        )
    ).all()
    result: dict[Any, list[dict[str, str]]] = {}
    for student_id, course, term, status in rows:
        result.setdefault(student_id, []).append({"course": course, "term": term, "status": status})
    return result


async def inbox(session: AsyncSession) -> list[Mirror]:
    """درخواست‌های ورودی (مسئله / همکاری) — چشم مالک روی `00_Inbox`."""
    rows = (
        await session.execute(
            select(IntakeRequest, User.person_code)
            .outerjoin(User, User.id == IntakeRequest.user_id)
            .order_by(IntakeRequest.created_at.desc())
        )
    ).all()
    out: list[Mirror] = []
    for request, person_code in rows:
        details = NEWLINE.join(
            f"- **{key}:** {value if not isinstance(value, list) else '، '.join(map(str, value))}"
            for key, value in request.payload.items()
        )
        out.append(
            Mirror(
                folder="00_Inbox",
                name=f"{request.tracking_code} {request.need_type or ''} — {request.contact_name}",
                meta={
                    "type": "collaboration" if request.kind == "COLLABORATION" else "intake",
                    "tracking_code": request.tracking_code,
                    "status": request.status,
                    "person_code": person_code,
                    "contact_name": request.contact_name,
                    "mobile": request.contact_mobile,
                    "email": request.contact_email,
                    "organization": request.organization,
                    "need_type": request.need_type,
                    "services": list(request.services),
                    "received": request.created_at.strftime("%Y-%m-%d %H:%M"),
                },
                body=NEWLINE.join([f"# {request.tracking_code}", "", request.summary, "", details]),
            )
        )
    return out


async def courses(session: AsyncSession) -> list[Mirror]:
    counts = dict(
        (
            await session.execute(
                select(Enrollment.offering_id, func.count())
                .where(Enrollment.status == "ACTIVE")
                .group_by(Enrollment.offering_id)
            )
        )
        .tuples()
        .all()
    )
    rows = (
        await session.execute(
            select(Course, CourseOffering, Term)
            .join(CourseOffering, CourseOffering.course_id == Course.id, isouter=True)
            .join(Term, Term.id == CourseOffering.term_id, isouter=True)
            .where(Course.deleted_at.is_(None))
            .order_by(Course.title_fa, Term.starts_on.desc())
        )
    ).all()
    grouped: dict[Any, tuple[Course, list[str]]] = {}
    for course, offering, term in rows:
        entry = grouped.setdefault(course.id, (course, []))
        if offering is not None and term is not None:
            entry[1].append(
                f"- {term.title_fa}: {offering.status} — {counts.get(offering.id, 0)} دانشجوی فعال"
            )
    return [
        Mirror(
            folder="05_Courses",
            name=course.title_fa,
            meta={
                "type": "course",
                "slug": course.slug,
                "code": course.code,
                "source_dir": course.source_dir,
            },
            body="# " + course.title_fa + "\n\n## ارائه‌ها\n" + ("\n".join(lines) or "—"),
        )
        for course, lines in grouped.values()
    ]


async def projects(session: AsyncSession) -> list[Mirror]:
    rows = (
        await session.execute(
            select(Project, Profile)
            .outerjoin(Profile, Profile.user_id == Project.lead_id)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.created_at.desc())
        )
    ).all()
    return [
        Mirror(
            folder="04_Projects",
            name=project.title_fa,
            meta={
                "type": "project",
                "slug": project.slug,
                "kind": project.kind,
                "status": project.status,
                "lead": f"{lead.first_name} {lead.last_name}" if lead else None,
            },
            body="# " + project.title_fa + "\n\n" + project.summary,
        )
        for project, lead in rows
    ]


async def dashboard(session: AsyncSession) -> list[Mirror]:
    student_count = await session.scalar(
        select(func.count(func.distinct(UserRole.user_id))).where(
            UserRole.role_code == Role.STUDENT.value
        )
    )
    content = dict(
        (
            await session.execute(
                select(ContentItem.status, func.count()).group_by(ContentItem.status)
            )
        )
        .tuples()
        .all()
    )
    project_count = await session.scalar(
        select(func.count()).select_from(Project).where(Project.deleted_at.is_(None))
    )
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    body = (
        "# پیشخوان\n\n"
        f"- دانشجویان: {student_count or 0}\n"
        f"- پروژه‌ها: {project_count or 0}\n"
        f"- محتوا: منتشرشده {content.get('PUBLISHED', 0)} · پیش‌نویس {content.get('DRAFT', 0)}"
        f" · آرشیو {content.get('ARCHIVED', 0)}\n\n"
        f"آخرین صدور: {now}\n"
    )
    return [Mirror(folder=".", name="DASHBOARD", meta={"type": "dashboard"}, body=body)]


Exporter = Callable[[AsyncSession], Awaitable[list[Mirror]]]
EXPORTERS: dict[str, Exporter] = {
    "students": students,
    "inbox": inbox,
    "courses": courses,
    "projects": projects,
    "dashboard": dashboard,
}


async def export_vault(
    session: AsyncSession, vault: Path, *, only: tuple[str, ...] = ()
) -> ExportReport:
    report = ExportReport()
    for name, exporter in EXPORTERS.items():
        if only and name not in only:
            continue
        part = write_mirrors(vault, await exporter(session))
        report.written += part.written
        report.unchanged += part.unchanged
    return report


__all__ = [
    "EXPORTERS",
    "ExportReport",
    "Mirror",
    "export_vault",
    "render",
    "safe_name",
    "write_mirrors",
]
