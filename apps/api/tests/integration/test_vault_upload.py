"""آپلود Vault روی سرور با توکن برنامه‌ای — ADR-0031.

PostgreSQL واقعی لازم است (ایندکس یکتای `slug` و `token_hash`، آرایهٔ `scopes`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select
from tests.integration.helpers import grant_role, login, me

from silp.core.exceptions import InvalidToken, PermissionDenied
from silp.models.admin import AuditLog
from silp.models.api_token import ApiToken
from silp.models.content import ContentItem
from silp.services.api_token_service import ApiTokenService

pytestmark = pytest.mark.integration

OWNER = "09121990001"
STUDENT = "09121990002"
URL = "/api/v1/vault/publish"


def _note(name: str, slug: str, *, status: str = "published", title: str | None = None) -> dict:
    title = title or f"یادداشت آزمایشی {slug}"
    raw = f"---\ntitle: {title}\nstatus: {status}\nslug: {slug}\n---\n\nمتن یادداشت آزمایشی.\n"
    return {"path": f"12_Content/{name}", "raw": raw}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _owner_token(client: Any, session: Any, *, mobile: str = OWNER, admin: bool = True):  # type: ignore[no-untyped-def]
    jwt = await login(client, mobile)
    user_id = uuid.UUID(str((await me(client, jwt))["id"]))
    if admin:
        await grant_role(session, user_id, "ADMIN")
    row, raw = await ApiTokenService(session).create(
        user_id, name="رایانهٔ آزمایشی", scopes=["vault:publish"]
    )
    return user_id, row, raw


# ── احراز هویت ──────────────────────────────────────────────────────────
async def test_no_token_and_a_session_jwt_are_both_rejected(client, db_session) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post(URL, json={"notes": []})).status_code == 401
    jwt = await login(client, OWNER)
    user_id = uuid.UUID(str((await me(client, jwt))["id"]))
    await grant_role(db_session, user_id, "ADMIN")
    # مرورگر و ابزار خودکار دو مسیر جدا دارند.
    denied = await client.post(URL, json={"notes": []}, headers=_bearer(jwt))
    assert denied.status_code == 401


async def test_a_garbage_or_unknown_token_is_401(client) -> None:  # type: ignore[no-untyped-def]
    for token in ("nope", "silp_pat_" + "x" * 43):
        response = await client.post(URL, json={"notes": []}, headers=_bearer(token))
        assert response.status_code == 401, token


async def test_a_non_admin_owner_of_a_token_gets_403(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, _, raw = await _owner_token(client, db_session, mobile=STUDENT, admin=False)
    response = await client.post(URL, json={"notes": []}, headers=_bearer(raw))
    assert response.status_code == 403
    assert response.json()["error"]["details"]["permission"] == "content.publish"


async def test_losing_the_admin_role_kills_the_token_immediately(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.identity import UserRole
    from silp.services import authz

    user_id, _, raw = await _owner_token(client, db_session)
    ok = await client.post(URL, json={"notes": []}, headers=_bearer(raw))
    assert ok.status_code == 200, ok.text

    await db_session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    await db_session.flush()
    await authz.invalidate_roles(user_id)
    assert (await client.post(URL, json={"notes": []}, headers=_bearer(raw))).status_code == 403


async def test_a_revoked_token_is_401(client, db_session) -> None:  # type: ignore[no-untyped-def]
    user_id, row, raw = await _owner_token(client, db_session)
    assert await ApiTokenService(db_session).revoke(row.id, user_id=user_id)
    assert (await client.post(URL, json={"notes": []}, headers=_bearer(raw))).status_code == 401


async def test_someone_elses_token_cannot_be_revoked(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, row, raw = await _owner_token(client, db_session)
    assert not await ApiTokenService(db_session).revoke(row.id, user_id=uuid.uuid4())
    assert (await client.post(URL, json={"notes": []}, headers=_bearer(raw))).status_code == 200


async def test_expired_token_is_401(client, db_session) -> None:  # type: ignore[no-untyped-def]
    user_id, row, raw = await _owner_token(client, db_session)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    assert (await client.post(URL, json={"notes": []}, headers=_bearer(raw))).status_code == 401


async def test_only_the_hash_is_stored_and_a_wrong_scope_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, row, raw = await _owner_token(client, db_session)
    assert raw not in (row.token_hash, row.token_hint)
    assert raw.startswith(row.token_hint)
    assert len(row.token_hash) == 64
    svc = ApiTokenService(db_session)
    with pytest.raises(PermissionDenied):
        await svc.authenticate(raw, scope="something:else")
    with pytest.raises(InvalidToken):
        await svc.authenticate("silp_pat_unknown", scope="vault:publish")


async def test_unknown_scope_cannot_be_minted(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.core.exceptions import ValidationFailed

    jwt = await login(client, OWNER)
    user_id = uuid.UUID(str((await me(client, jwt))["id"]))
    with pytest.raises(ValidationFailed):
        await ApiTokenService(db_session).create(user_id, name="x", scopes=["admin:everything"])


# ── انتشار ──────────────────────────────────────────────────────────────
async def test_default_is_a_preview_that_writes_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, _, raw = await _owner_token(client, db_session)
    body = {"notes": [_note("a.md", "up-preview")]}
    response = await client.post(URL, json=body, headers=_bearer(raw))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["applied"] is False
    assert data["created"] == ["12_Content/a.md"]
    assert (await client.get("/api/v1/public/content/up-preview")).status_code == 404


async def test_apply_publishes_and_a_repeat_is_a_no_op(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, _, raw = await _owner_token(client, db_session)
    body = {
        "apply": True,
        "notes": [_note("a.md", "up-one"), _note("b.md", "up-two", status="draft")],
    }
    first = (await client.post(URL, json=body, headers=_bearer(raw))).json()
    assert first["applied"] is True and first["ok"] is True
    assert sorted(first["created"]) == ["12_Content/a.md", "12_Content/b.md"]
    assert (await client.get("/api/v1/public/content/up-one")).status_code == 200
    assert (await client.get("/api/v1/public/content/up-two")).status_code == 404  # پیش‌نویس

    second = (await client.post(URL, json=body, headers=_bearer(raw))).json()
    assert second["created"] == [] and second["updated"] == []
    assert len(second["unchanged"]) == 2


async def test_the_server_parses_and_one_bad_note_does_not_block_the_rest(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    _, _, raw = await _owner_token(client, db_session)
    bad_raw = "---\ntitle: خراب آزمایشی\nkind: podcast\n---\nمتن\n"
    bad = {"path": "12_Content/bad.md", "raw": bad_raw}
    body = {"apply": True, "notes": [_note("ok.md", "up-ok"), bad]}
    data = (await client.post(URL, json=body, headers=_bearer(raw))).json()
    assert data["created"] == ["12_Content/ok.md"]
    assert "kind" in data["errors"]["12_Content/bad.md"]
    assert data["ok"] is False


async def test_template_and_hidden_files_are_ignored(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, _, raw = await _owner_token(client, db_session)
    body = {
        "apply": True,
        "notes": [_note("_template.md", "up-tpl"), _note(".hid/x.md", "up-hid")],
    }
    data = (await client.post(URL, json=body, headers=_bearer(raw))).json()
    assert data["created"] == [] and data["errors"] == {}


async def test_archive_needs_complete_and_client_errors_are_protected(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    _, _, raw = await _owner_token(client, db_session)
    keep = _note("keep.md", "up-keep")
    gone = _note("gone.md", "up-gone")
    await client.post(URL, json={"apply": True, "notes": [keep, gone]}, headers=_bearer(raw))

    partial = await client.post(URL, json={"apply": True, "notes": [keep]}, headers=_bearer(raw))
    assert partial.json()["archived"] == []  # فهرست ناقص هرگز آرشیو نمی‌کند

    protected = await client.post(
        URL,
        json={
            "apply": True,
            "complete": True,
            "notes": [keep],
            "client_errors": {"12_Content/gone.md": "فایل UTF-8 نیست."},
        },
        headers=_bearer(raw),
    )
    assert protected.json()["archived"] == []
    assert "UTF-8" in protected.json()["errors"]["12_Content/gone.md"]

    full = await client.post(
        URL, json={"apply": True, "complete": True, "notes": [keep]}, headers=_bearer(raw)
    )
    assert full.json()["archived"] == ["12_Content/gone.md"]
    row = await db_session.scalar(select(ContentItem).where(ContentItem.slug == "up-gone"))
    assert row is not None and row.status == "ARCHIVED"


async def test_oversized_and_off_folder_paths_are_rejected(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, _, raw = await _owner_token(client, db_session)
    for path in ("02_Students/a.md", "12_Content/a.txt", "12_Content/..\\a.md"):
        response = await client.post(
            URL, json={"notes": [{"path": path, "raw": "x"}]}, headers=_bearer(raw)
        )
        assert response.status_code == 422, path
    too_big = {"path": "12_Content/big.md", "raw": "a" * 300_001}
    assert (
        await client.post(URL, json={"notes": [too_big]}, headers=_bearer(raw))
    ).status_code == 422


async def test_apply_leaves_an_audit_row_and_a_preview_does_not(client, db_session) -> None:  # type: ignore[no-untyped-def]
    user_id, _, raw = await _owner_token(client, db_session)
    body = {"notes": [_note("a.md", "up-audit")]}
    await client.post(URL, json=body, headers=_bearer(raw))
    rows = list(
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.actor_id == user_id, AuditLog.action == "CONTENT_PUBLISHED"
            )
        )
    )
    assert rows == []

    await client.post(URL, json={**body, "apply": True}, headers=_bearer(raw))
    rows = list(
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.actor_id == user_id, AuditLog.action == "CONTENT_PUBLISHED"
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].after["created"] == ["12_Content/a.md"]


# ── پایداری: از اتصال دیگر ─────────────────────────────────────────────
async def test_apply_survives_the_request(committing_client, committing_session) -> None:  # type: ignore[no-untyped-def]
    """commit فراموش‌شده در `client` معمولی دیده نمی‌شود؛ اینجا از اتصال جدا می‌خوانیم."""
    from silp.db.session import get_session_factory
    from silp.models.identity import User

    mobile = f"0912{uuid.uuid4().int % 10_000_000:07d}"
    slug = f"dur-{uuid.uuid4().hex[:8]}"
    jwt = await login(committing_client, mobile)
    user_id = uuid.UUID(str((await me(committing_client, jwt))["id"]))
    try:
        await grant_role(committing_session, user_id, "ADMIN")
        await committing_session.commit()
        _, raw = await ApiTokenService(committing_session).create(
            user_id, name="پایداری", scopes=["vault:publish"]
        )
        await committing_session.commit()

        response = await committing_client.post(
            URL,
            json={"apply": True, "notes": [_note("dur.md", slug)]},
            headers=_bearer(raw),
        )
        assert response.status_code == 200, response.text

        async with get_session_factory()() as other:
            row = await other.scalar(select(ContentItem).where(ContentItem.slug == slug))
            assert row is not None and row.status == "PUBLISHED"
            audit = await other.scalar(
                select(AuditLog).where(
                    AuditLog.actor_id == user_id, AuditLog.action == "CONTENT_PUBLISHED"
                )
            )
            assert audit is not None
            token = await other.scalar(select(ApiToken).where(ApiToken.user_id == user_id))
            assert token is not None and token.last_used_at is not None
    finally:
        await committing_session.execute(delete(ContentItem).where(ContentItem.slug == slug))
        await committing_session.execute(delete(User).where(User.id == user_id))
        await committing_session.commit()
