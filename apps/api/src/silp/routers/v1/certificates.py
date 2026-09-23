"""مسیرهای گواهی — FR-PRJ-08، §5.3، §5.3.1، M7-11، ADR-0017.

| مسیر | دسترسی |
|------|--------|
| `GET /public/certificates/{code}` | همه، بی‌ورود — راستی‌آزمایی |
| `GET /me/certificates` | خود دارنده، با باطل‌شده‌ها |
| `GET /admin/certificates` | `certificate.revoke` — جستجو با کد یا کاربر |
| `POST /admin/certificates/{id}/revoke` | `certificate.revoke` — با دلیل و لاگ حسابرسی |

گواهی صادر نمی‌شود مگر از رویداد (`certificate_listeners`)؛ مسیر صدور
دستی عمداً نیست — گواهی‌ای که کسی بی‌رویداد صادر کند، چیزی را اثبات نمی‌کند.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import select

from silp.core.permissions import CurrentUser, Permission
from silp.models.delivery import CERTIFICATE_KIND_TITLE_FA, Certificate
from silp.routers.deps import CurrentUserDep, SessionDep, require
from silp.schemas.common import ErrorResponse
from silp.schemas.public import CertificateOut, CertificateRevokeIn, CertificateVerifyOut
from silp.services.certificate_service import ISSUER_FALLBACK_FA, CertificateService
from silp.services.directory import display_names, name_of

public_router = APIRouter(prefix="/public/certificates", tags=["public"])
me_router = APIRouter(prefix="/me/certificates", tags=["me"])
admin_router = APIRouter(prefix="/admin/certificates", tags=["admin"])


def verify_path(code: str) -> str:
    return f"/verify/{code}"


async def certificates_out(session: SessionDep, rows: list[Certificate]) -> list[CertificateOut]:
    names = await display_names(session, [c.issued_by for c in rows])
    return [
        CertificateOut(
            id=c.id,
            public_code=c.public_code,
            kind=c.kind,
            kind_fa=CERTIFICATE_KIND_TITLE_FA[c.kind],
            title_fa=c.title_fa,
            issued_at=c.issued_at,
            issuer_name=name_of(names, c.issued_by) or ISSUER_FALLBACK_FA,
            verify_path=verify_path(c.public_code),
            details=c.meta,
            revoked_at=c.revoked_at,
            revoke_reason=c.revoke_reason,
        )
        for c in rows
    ]


@public_router.get(
    "/{code}",
    response_model=CertificateVerifyOut,
    summary="راستی‌آزمایی گواهی",
    responses={404: {"model": ErrorResponse, "description": "کدی که هرگز صادر نشده"}},
)
async def verify_certificate(
    code: Annotated[str, Path(min_length=4, max_length=20)],
    session: SessionDep,
    response: Response,
) -> CertificateVerifyOut:
    result = await CertificateService(session).verify(code)
    c = result.certificate
    # ابطال باید زود دیده شود؛ کش کوتاه.
    response.headers["Cache-Control"] = "public, max-age=60"
    return CertificateVerifyOut(
        valid=c.revoked_at is None,
        public_code=c.public_code,
        kind=c.kind,
        kind_fa=CERTIFICATE_KIND_TITLE_FA[c.kind],
        title_fa=c.title_fa,
        holder_name=result.holder_name,
        holder_username=result.holder_username,
        issued_at=c.issued_at,
        issuer=result.issuer_name,
        details=c.meta,
        revoked_at=c.revoked_at,
        revoke_reason=c.revoke_reason,
    )


@me_router.get("", response_model=list[CertificateOut], summary="گواهی‌های من")
async def my_certificates(current: CurrentUserDep, session: SessionDep) -> list[CertificateOut]:
    rows = await CertificateService(session).for_user(current.id, include_revoked=True)
    return await certificates_out(session, rows)


@admin_router.get(
    "",
    response_model=list[CertificateOut],
    summary="جستجوی گواهی",
    responses={403: {"model": ErrorResponse}},
)
async def search_certificates(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.CERTIFICATE_REVOKE))],
    code: Annotated[str | None, Query(max_length=20)] = None,
    user_id: uuid.UUID | None = None,
) -> list[CertificateOut]:
    service = CertificateService(session)
    if code:
        found = await service.by_code(code)
        return await certificates_out(session, [found] if found else [])
    stmt = select(Certificate).order_by(Certificate.issued_at.desc()).limit(50)
    if user_id is not None:
        stmt = stmt.where(Certificate.user_id == user_id)
    return await certificates_out(session, list(await session.scalars(stmt)))


@admin_router.post(
    "/{certificate_id}/revoke",
    response_model=CertificateOut,
    summary="ابطال گواهی",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def revoke_certificate(
    certificate_id: uuid.UUID,
    payload: CertificateRevokeIn,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.CERTIFICATE_REVOKE))],
) -> CertificateOut:
    certificate = await CertificateService(session).revoke(
        certificate_id=certificate_id, actor=actor, reason=payload.reason
    )
    return (await certificates_out(session, [certificate]))[0]


__all__ = ["admin_router", "me_router", "public_router"]
