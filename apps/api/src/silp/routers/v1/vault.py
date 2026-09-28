"""انتشار Vault از رایانهٔ مالک روی سرور — ADR-0031.

| مسیر | احراز هویت |
|------|-------------|
| `POST /vault/publish` | توکن برنامه‌ای با دامنهٔ `vault:publish`، صاحبش `content.publish` |

بدنه: متن خام فایل‌های `12_Content` (نه نتیجهٔ تحلیل ابزار). سرور خودش تحلیل می‌کند
و همان `publish_notes`ی را صدا می‌زند که `vault publish` روی دیسک صدا می‌زند؛ پس
رفتار (بی‌اثر در تکرار، آرشیو، خطای هر یادداشت) یکی است.

پیش‌فرض **پیش‌نمایش** است (`apply=false`)؛ آرشیو فقط اگر ابزار بگوید فهرست کامل
است (`complete=true`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from silp.core.permissions import CurrentUser, Permission
from silp.domain import audit
from silp.routers.deps import SessionDep, require_token
from silp.schemas.common import ErrorResponse
from silp.schemas.vault import VaultPublishIn, VaultPublishOut
from silp.services.audit_service import AuditService
from silp.vault.notes import CONTENT_DIR
from silp.vault.publisher import parse_files, publish_notes

router = APIRouter(
    prefix="/vault",
    tags=["vault"],
    responses={
        401: {"model": ErrorResponse, "description": "توکن نامعتبر"},
        403: {"model": ErrorResponse, "description": "دامنه یا مجوز کافی نیست"},
    },
)

PublisherDep = Annotated[
    CurrentUser, Depends(require_token("vault:publish", Permission.CONTENT_PUBLISH))
]


@router.post("/publish", response_model=VaultPublishOut, summary="انتشار یادداشت‌های Vault")
async def publish(
    payload: VaultPublishIn, session: SessionDep, user: PublisherDep, response: Response
) -> VaultPublishOut:
    response.headers["Cache-Control"] = "no-store"
    notes, errors = parse_files((n.path, n.raw) for n in payload.notes)
    errors.update(payload.client_errors)
    # پیش‌نمایش در SAVEPOINT اجرا و برگردانده می‌شود، نه کل نشست: `last_used_at` توکن که
    # هنگام احراز هویت نوشته شده، در هر دو حالت commit می‌شود.
    savepoint = await session.begin_nested()
    report = await publish_notes(
        session,
        notes,
        seen_errors=errors,
        archive_missing=payload.complete and CONTENT_DIR not in errors,
    )
    if payload.apply:
        if report.created or report.updated or report.archived:
            AuditService(session).stage(
                audit.CONTENT_PUBLISHED,
                actor=user,
                entity_type="CONTENT",
                after={
                    "created": report.created,
                    "updated": report.updated,
                    "archived": report.archived,
                },
            )
        await savepoint.commit()
    else:
        await savepoint.rollback()
    await session.commit()
    return VaultPublishOut(
        applied=payload.apply,
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        archived=report.archived,
        errors=report.errors,
        warnings={path: list(w) for path, w in report.warnings.items()},
        ok=report.ok,
    )


__all__ = ["router"]
