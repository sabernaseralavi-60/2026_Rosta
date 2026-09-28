"""پیام گروهی مالک — ADR-0030.

یک فایل در `14_AI/broadcasts/` = یک پیام. مخاطب در سرآیند مشخص می‌شود::

    ---
    title: یادآوری آزمون هفتهٔ ۵
    audience: students        # students | all | offering:<شناسه> | user:<موبایل>
    ---
    متن پیام…

**امنیت (بیرون‌رونده = برگشت‌ناپذیر):**

* بدون `send=True` هیچ‌چیز نوشته نمی‌شود؛ فقط شمار مخاطب و پیش‌نمایش برمی‌گردد.
* `dedup_key` از محتوای پیام و مخاطب ساخته می‌شود؛ اجرای دوبارهٔ همان فایل برای
  هیچ‌کس پیام دوم نمی‌سازد. متن را عوض کنید تا پیام تازه‌ای باشد.
* پیامک ندارد (`OWNER_BROADCAST.allow_sms=False`)؛ کانال‌ها همان ترجیح کاربرند.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.permissions import Role
from silp.models.education import Enrollment
from silp.models.identity import User, UserRole
from silp.services.notification_service import NotificationService
from silp.vault.notes import NoteError, split_frontmatter

BROADCAST_DIR = "14_AI/broadcasts"
LOG_NAME = "14_AI/broadcast-log.md"
_AUDIENCE = re.compile(r"^(students|all|offering:[0-9a-fA-F-]{36}|user:09\d{9})$")


@dataclass(frozen=True, slots=True)
class Broadcast:
    title: str
    body: str
    audience: str

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256(f"{self.audience}\n{self.title}\n{self.body}".encode()).hexdigest()
        return digest[:20]

    @property
    def dedup_key(self) -> str:
        return f"BROADCAST:{self.fingerprint}"


@dataclass(slots=True)
class BroadcastResult:
    audience: str
    recipients: int
    sent: bool
    created: int = 0
    already_received: int = 0


def load_broadcast(path: Path) -> Broadcast:
    if not path.is_file():
        raise NoteError(f"فایل پیدا نشد: {path}")
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    title = str(meta.get("title") or "").strip()
    audience = str(meta.get("audience") or "").strip()
    body = body.strip()
    if not title:
        raise NoteError("«title» لازم است.")
    if not body:
        raise NoteError("متن پیام خالی است.")
    if not _AUDIENCE.match(audience):
        raise NoteError(
            "«audience» باید یکی از این‌ها باشد: students، all، offering:<شناسه>، user:<موبایل>"
        )
    return Broadcast(title=title, body=body, audience=audience)


async def resolve_audience(session: AsyncSession, audience: str) -> list[uuid.UUID]:
    active = User.status == "ACTIVE", User.deleted_at.is_(None)
    if audience == "all":
        statement = select(User.id).where(*active)
    elif audience == "students":
        statement = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_code == Role.STUDENT.value, *active)
        )
    elif audience.startswith("offering:"):
        statement = (
            select(User.id)
            .join(Enrollment, Enrollment.student_id == User.id)
            .where(
                Enrollment.offering_id == uuid.UUID(audience.split(":", 1)[1]),
                Enrollment.status == "ACTIVE",
                *active,
            )
        )
    else:
        statement = select(User.id).where(User.mobile == audience.split(":", 1)[1], *active)
    return list(dict.fromkeys(await session.scalars(statement)))


async def run_broadcast(
    session: AsyncSession, message: Broadcast, *, send: bool
) -> BroadcastResult:
    recipients = await resolve_audience(session, message.audience)
    result = BroadcastResult(audience=message.audience, recipients=len(recipients), sent=send)
    if not send or not recipients:
        return result
    created = await NotificationService(session).notify(
        "OWNER_BROADCAST",
        recipients,
        {"title": message.title, "body": message.body},
        dedup_key=message.dedup_key,
    )
    result.created = len(created)
    result.already_received = len(recipients) - len(created)
    return result


def append_log(vault: Path, message: Broadcast, result: BroadcastResult) -> None:
    """ثبت در `broadcast-log.md` — تنها ردّ ارسال‌ها روی رایانهٔ مالک."""
    target = vault / LOG_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("# گزارش پیام‌های گروهی\n\n", encoding="utf-8", newline="\n")
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    line = (
        f"- {stamp} — «{message.title}» ← {message.audience}: "
        f"{result.created} پیام تازه، {result.already_received} قبلاً دریافت‌شده"
        f" (`{message.fingerprint}`)\n"
    )
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


__all__ = [
    "BROADCAST_DIR",
    "Broadcast",
    "BroadcastResult",
    "append_log",
    "load_broadcast",
    "resolve_audience",
    "run_broadcast",
]
