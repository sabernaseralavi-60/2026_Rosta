"""آپلود و پیوست فایل — FR-EDU-03، §5.9، §11.1، M2-08.

`storage` همان آداپتور حافظه‌ای است که اپ استفاده می‌کند، پس تست دقیقاً
نقش کلاینت آپلودکننده را بازی می‌کند: بعد از `upload-url` خودش شیء را
می‌نویسد و سپس `complete` می‌زند.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.helpers import (
    auth,
    complete_profile,
    invalidate,
    login,
    me,
    milestone_payload,
    project_payload,
    taxonomy_ids,
)

pytestmark = pytest.mark.integration

OWNER = "09121550001"
OTHER = "09121550002"

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


async def _reserve(
    client: Any,
    token: str,
    *,
    name: str = "report.pdf",
    content_type: str = "application/pdf",
    size: int = len(PDF_BYTES),
    purpose: str = "DELIVERABLE",
) -> Any:
    return await client.post(
        "/api/v1/files/upload-url",
        headers=auth(token),
        json={
            "original_name": name,
            "content_type": content_type,
            "size_bytes": size,
            "purpose": purpose,
        },
    )


def _key_of(storage: Any) -> str:
    return next(iter(storage.objects))


async def _upload(client: Any, storage: Any, token: str, **kwargs: Any) -> str:
    """رزرو، نوشتن روی فضای ذخیره‌سازی، و تکمیل. خروجی: شناسهٔ فایل."""
    body = kwargs.pop("body", PDF_BYTES)
    reserved = await _reserve(client, token, size=len(body), **kwargs)
    assert reserved.status_code == 200, reserved.text
    payload = reserved.json()

    key = payload["upload_url"].split("/", 3)[-1]
    storage.put_object(key, body, payload["headers"]["Content-Type"])

    completed = await client.post(
        f"/api/v1/files/{payload['file_id']}/complete", headers=auth(token)
    )
    assert completed.status_code == 200, completed.text
    return str(payload["file_id"])


# ── رزرو ───────────────────────────────────────────────────────────────
async def test_upload_url_carries_everything_the_client_needs(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    response = await _reserve(client, token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "PUT"
    assert body["headers"]["Content-Type"] == "application/pdf"
    assert body["expires_in"] > 0
    assert body["max_bytes"] == 50 * 1024 * 1024


async def test_oversized_file_is_refused_before_upload(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    response = await _reserve(client, token, size=200 * 1024 * 1024)

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert response.json()["error"]["details"]["max_bytes"] == 50 * 1024 * 1024


async def test_disallowed_content_type_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    response = await _reserve(
        client, token, name="app.exe", content_type="application/x-msdownload"
    )

    assert response.status_code == 415, response.text
    assert response.json()["error"]["code"] == "CONTENT_TYPE_NOT_ALLOWED"


async def test_avatar_rejects_a_video(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    response = await _reserve(
        client, token, name="clip.mp4", content_type="video/mp4", purpose="AVATAR"
    )
    assert response.status_code == 415, response.text


# ── تکمیل ──────────────────────────────────────────────────────────────
async def test_complete_verifies_the_magic_number(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    """§11.1 — پسوند و هدر حرف کاربرند؛ بایت‌های فایل حقیقت‌اند."""
    token = await login(client, OWNER)
    reserved = await _reserve(client, token)
    payload = reserved.json()
    key = payload["upload_url"].split("/", 3)[-1]
    # فایل اجرایی با پسوند pdf آپلود می‌شود.
    storage.put_object(key, b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf")

    response = await client.post(
        f"/api/v1/files/{payload['file_id']}/complete", headers=auth(token)
    )
    assert response.status_code == 415, response.text
    assert response.json()["error"]["code"] == "CONTENT_TYPE_NOT_ALLOWED"
    # فایل مشکوک نگه داشته نمی‌شود.
    assert key not in storage.objects


async def test_complete_without_an_upload_is_a_conflict(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    reserved = await _reserve(client, token)

    response = await client.post(
        f"/api/v1/files/{reserved.json()['file_id']}/complete", headers=auth(token)
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UPLOAD_INCOMPLETE"


async def test_complete_records_the_real_size(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    """حجم ادعایی کلاینت جایگزین حجم واقعی شیء نمی‌شود."""
    token = await login(client, OWNER)
    reserved = await _reserve(client, token, size=10)
    payload = reserved.json()
    key = payload["upload_url"].split("/", 3)[-1]
    storage.put_object(key, PDF_BYTES, "application/pdf")

    response = await client.post(
        f"/api/v1/files/{payload['file_id']}/complete", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["size_bytes"] == len(PDF_BYTES)
    assert response.json()["uploaded_at"] is not None


async def test_complete_is_idempotent(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    """دو بار کلیک روی «تمام شد»، یک نتیجه."""
    token = await login(client, OWNER)
    file_id = await _upload(client, storage, token)

    again = await client.post(f"/api/v1/files/{file_id}/complete", headers=auth(token))
    assert again.status_code == 200, again.text
    assert again.json()["id"] == file_id


async def test_another_user_cannot_complete_someone_elses_upload(  # type: ignore[no-untyped-def]
    client, db_session, storage
) -> None:
    """§6.4 قاعدهٔ ۴ — ۴۰۴، نه ۴۰۳."""
    owner_token = await login(client, OWNER)
    other_token = await login(client, OTHER)
    reserved = await _reserve(client, owner_token)

    response = await client.post(
        f"/api/v1/files/{reserved.json()['file_id']}/complete", headers=auth(other_token)
    )
    assert response.status_code == 404, response.text


# ── دانلود و حذف ───────────────────────────────────────────────────────
async def test_download_url_is_issued_for_the_owner_only(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    owner_token = await login(client, OWNER)
    other_token = await login(client, OTHER)
    file_id = await _upload(client, storage, owner_token)

    mine = await client.get(f"/api/v1/files/{file_id}/download-url", headers=auth(owner_token))
    assert mine.status_code == 200, mine.text
    assert mine.json()["original_name"] == "report.pdf"

    theirs = await client.get(f"/api/v1/files/{file_id}/download-url", headers=auth(other_token))
    assert theirs.status_code == 404, theirs.text


async def test_soft_deleted_file_is_gone_from_the_api(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    file_id = await _upload(client, storage, token)

    removed = await client.delete(f"/api/v1/files/{file_id}", headers=auth(token))
    assert removed.status_code == 204, removed.text

    response = await client.get(f"/api/v1/files/{file_id}/download-url", headers=auth(token))
    assert response.status_code == 404, response.text


# ── پیوست به تحویل‌دادنی ───────────────────────────────────────────────
async def _running_project(client: Any, token: str) -> str:
    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(token),
        json=project_payload(required_skills=[{"skill_id": skills[0], "min_level": 3}]),
    )
    project_id = created.json()["id"]
    milestone = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(token),
        json=milestone_payload(),
    )
    await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(token))
    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(token))
    return str(milestone.json()["id"])


async def test_deliverable_carries_its_attachments(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OWNER)
    await complete_profile(client, token)
    await invalidate(str((await me(client, token))["id"]))
    milestone_id = await _running_project(client, token)
    file_id = await _upload(client, storage, token)

    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(token),
        json={"body": "گزارش با پیوست", "file_ids": [file_id]},
    )
    assert response.status_code == 201, response.text
    files = response.json()["files"]
    assert [f["id"] for f in files] == [file_id]
    assert files[0]["original_name"] == "report.pdf"

    listed = await client.get(
        f"/api/v1/milestones/{milestone_id}/deliverables", headers=auth(token)
    )
    assert [f["id"] for f in listed.json()[0]["files"]] == [file_id]


async def test_unfinished_upload_cannot_be_attached(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    """فایل رزروشده‌ای که هرگز آپلود نشد، نباید به تحویل‌دادنی بچسبد."""
    token = await login(client, OWNER)
    await complete_profile(client, token)
    await invalidate(str((await me(client, token))["id"]))
    milestone_id = await _running_project(client, token)
    reserved = await _reserve(client, token)

    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(token),
        json={"body": "گزارش", "file_ids": [reserved.json()["file_id"]]},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UPLOAD_INCOMPLETE"


async def test_someone_elses_file_cannot_be_attached(client, db_session, storage) -> None:  # type: ignore[no-untyped-def]
    owner_token = await login(client, OWNER)
    await complete_profile(client, owner_token)
    await invalidate(str((await me(client, owner_token))["id"]))
    milestone_id = await _running_project(client, owner_token)

    other_token = await login(client, OTHER)
    foreign_file = await _upload(client, storage, other_token, body=PNG_BYTES,
                                 name="shot.png", content_type="image/png")

    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(owner_token),
        json={"body": "گزارش", "file_ids": [foreign_file]},
    )
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("count", [11])
async def test_too_many_attachments_are_refused(client, db_session, storage, count: int) -> None:  # type: ignore[no-untyped-def]
    """§11.8 — حداکثر ده فایل در هر تحویل‌دادنی."""
    token = await login(client, OWNER)
    await complete_profile(client, token)
    await invalidate(str((await me(client, token))["id"]))
    milestone_id = await _running_project(client, token)

    fake_ids = [f"018f0000-0000-7000-8000-{index:012d}" for index in range(count)]
    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(token),
        json={"body": "گزارش", "file_ids": fake_ids},
    )
    # اعتبارسنجی Pydantic پیش از رسیدن به سرویس جلویش را می‌گیرد.
    assert response.status_code == 422, response.text
