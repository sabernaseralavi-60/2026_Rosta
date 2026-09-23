"""گواهی: صدور، ابطال و راستی‌آزمایی — FR-PRJ-08، M7-11، ADR-0017.

صدور **بی‌اثر** است: ایندکس یکتای `uq_certificates_subject` («یک گواهی
معتبر برای هر موضوع») با `ON CONFLICT DO NOTHING` هدف قرار می‌گیرد؛ پس
بازپخش رویداد، اسکریپت پس‌پر کردن و دو تأیید هم‌زمان هیچ‌کدام گواهی دوم
نمی‌سازند. گواهی باطل‌شده پاک نمی‌شود — پیوندی که در رزومه‌ای مانده باید
بگوید «باطل شد»، نه «هرگز نبود» — و موضوعش می‌تواند دوباره گواهی بگیرد.

صفحهٔ راستی‌آزمایی عمومی است و فقط آنچه روی خود گواهی چاپ می‌شود را
برمی‌گرداند: نام دارنده، عنوان، تاریخ و صادرکننده. نه موبایل، نه نمره.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser
from silp.domain import audit
from silp.domain import certificates as rules
from silp.models.delivery import Certificate
from silp.models.identity import User
from silp.models.profile import Profile
from silp.services import events
from silp.services.audit_service import AuditService

log = get_logger("silp.certificates")

#: برخورد کد ۴۰ بیتی تقریباً ناممکن است؛ سه تلاش، نه حلقهٔ بی‌پایان.
CODE_ATTEMPTS = 3
ISSUER_FALLBACK_FA = "سامانهٔ نوآوری و یادگیری صابر"


@dataclass(frozen=True, slots=True)
class Verification:
    certificate: Certificate
    holder_name: str
    holder_username: str | None
    issuer_name: str


class CertificateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── صدور ───────────────────────────────────────────────────────────
    async def issue(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        subject_id: uuid.UUID,
        title_fa: str,
        issued_by: uuid.UUID | None,
        meta: dict[str, Any] | None = None,
        notify: bool = True,
    ) -> Certificate | None:
        """گواهی تازه، یا `None` اگر همین موضوع گواهی معتبر دارد.

        صادرکننده هرگز خود دارنده نیست: دانشجویی که پروژهٔ شخصی‌اش را خودش
        می‌بندد، گواهی‌اش را «سامانه» صادر کرده، نه خودش.
        """
        issuer = None if issued_by == user_id else issued_by
        for attempt in range(CODE_ATTEMPTS):
            statement = (
                insert(Certificate)
                .values(
                    public_code=rules.new_code(),
                    user_id=user_id,
                    kind=kind,
                    subject_id=subject_id,
                    title_fa=title_fa,
                    issued_by=issuer,
                    meta=meta or {},
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "kind", "subject_id"],
                    index_where=text("revoked_at IS NULL"),
                )
                .returning(Certificate.id)
            )
            try:
                async with self.session.begin_nested():
                    certificate_id = await self.session.scalar(statement)
            except IntegrityError:
                # فقط برخورد `public_code` به اینجا می‌رسد؛ موضوع تکراری را
                # `ON CONFLICT` بی‌صدا رد کرده است.
                log.warning("certificate_code_collision", attempt=attempt + 1)
                continue
            if certificate_id is None:
                return None
            certificate = await self.session.get(Certificate, certificate_id)
            assert certificate is not None
            log.info("certificate_issued", kind=kind, certificate_id=str(certificate_id))
            if notify:
                await events.publish(
                    self.session, events.CertificateIssued(certificate_id=certificate_id)
                )
            return certificate
        msg = "کد یکتای گواهی ساخته نشد."
        raise RuntimeError(msg)

    async def revoke_auto(
        self, *, user_id: uuid.UUID, kind: str, subject_id: uuid.UUID, reason: str
    ) -> None:
        """ابطال خودکار وقتی شرط صدور دیگر برقرار نیست — نمرهٔ درس اصلاح شد."""
        certificate = await self.session.scalar(
            select(Certificate).where(
                Certificate.user_id == user_id,
                Certificate.kind == kind,
                Certificate.subject_id == subject_id,
                Certificate.revoked_at.is_(None),
            )
        )
        if certificate is None:
            return
        certificate.revoked_at = datetime.now(UTC)
        certificate.revoke_reason = reason
        await events.publish(self.session, events.CertificateRevoked(certificate_id=certificate.id))

    # ── ابطال دستی — `POST /admin/certificates/{id}/revoke` ────────────
    async def revoke(
        self, *, certificate_id: uuid.UUID, actor: CurrentUser, reason: str
    ) -> Certificate:
        cleaned = reason.strip()
        if len(cleaned) < 5:
            raise ValidationFailed("دلیل ابطال را بنویسید — دست‌کم چند کلمه.")
        certificate = await self.session.get(Certificate, certificate_id, with_for_update=True)
        if certificate is None:
            raise NotFound("این گواهی پیدا نشد.")
        if certificate.revoked_at is not None:
            raise Conflict("این گواهی قبلاً باطل شده است.")
        certificate.revoked_at = datetime.now(UTC)
        certificate.revoked_by = actor.id
        certificate.revoke_reason = cleaned
        AuditService(self.session).stage(
            audit.CERTIFICATE_REVOKED,
            actor=actor,
            entity_type="CERTIFICATE",
            entity_id=certificate.id,
            before={"public_code": certificate.public_code, "revoked": False},
            after={"public_code": certificate.public_code, "revoked": True, "reason": cleaned},
        )
        await events.publish(self.session, events.CertificateRevoked(certificate_id=certificate.id))
        await self.session.commit()
        log.info("certificate_revoked", certificate_id=str(certificate.id))
        return certificate

    # ── خواندن ─────────────────────────────────────────────────────────
    async def for_user(self, user_id: uuid.UUID, *, include_revoked: bool) -> list[Certificate]:
        stmt = select(Certificate).where(Certificate.user_id == user_id)
        if not include_revoked:
            stmt = stmt.where(Certificate.revoked_at.is_(None))
        return list(await self.session.scalars(stmt.order_by(Certificate.issued_at.desc())))

    async def by_code(self, raw_code: str) -> Certificate | None:
        code = rules.normalize_code(raw_code)
        if code is None:
            return None
        found: Certificate | None = await self.session.scalar(
            select(Certificate).where(Certificate.public_code == code)
        )
        return found

    async def verify(self, raw_code: str) -> Verification:
        """`GET /public/certificates/{code}` — §5.3.1.

        گواهی باطل‌شده هم برمی‌گردد، با `revoked_at`؛ «یافت نشد» فقط برای
        کدی است که هرگز صادر نشده (ADR-0017).
        """
        certificate = await self.by_code(raw_code)
        if certificate is None:
            raise NotFound("گواهی با این کد پیدا نشد. کد را دوباره بررسی کن.")
        holder = await self._person(certificate.user_id)
        issuer = await self._person(certificate.issued_by) if certificate.issued_by else None
        return Verification(
            certificate=certificate,
            holder_name=holder[0] or "دارندهٔ گواهی",
            holder_username=holder[1],
            issuer_name=issuer[0] if issuer and issuer[0] else ISSUER_FALLBACK_FA,
        )

    async def _person(self, user_id: uuid.UUID | None) -> tuple[str | None, str | None]:
        """(نام کامل، نام کاربری اگر نیمرخ عمومی است).

        روی گواهی نام رسمی می‌آید، نه نام نمایشی — گواهی سند است.
        """
        if user_id is None:
            return None, None
        row = (
            await self.session.execute(
                select(Profile.first_name, Profile.last_name, Profile.is_public, User.username)
                .join(User, User.id == Profile.user_id)
                .where(Profile.user_id == user_id)
            )
        ).first()
        if row is None:
            return None, None
        first, last, is_public, username = row
        name = f"{first} {last}".strip() or None
        return name, username if is_public and username else None


__all__ = ["ISSUER_FALLBACK_FA", "CertificateService", "Verification"]
