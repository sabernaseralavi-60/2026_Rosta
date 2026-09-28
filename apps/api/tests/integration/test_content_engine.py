"""موتور محتوای Vault-محور، آینهٔ داده و پیام گروهی — ADR-0030.

PostgreSQL واقعی لازم است: ایندکس یکتای `slug` و `source_path`، ستون آرایه‌ای
`topics` با GIN و `fa_normalize` جست‌وجو در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select
from tests.integration.helpers import auth, complete_profile, grant_role, login, me

from silp.models.content import ContentItem
from silp.vault import broadcast as bcast
from silp.vault.exporter import export_vault
from silp.vault.publisher import publish_vault
from silp.vault.skeleton import init_vault

pytestmark = pytest.mark.integration

STUDENT = "09121880001"
OUTSIDER = "09121880002"
STAFF = "09121880003"
SLUG = f"t-{uuid.uuid4().hex[:8]}"


def _write(
    vault: Path, name: str, meta: dict[str, str], body: str = "متن یادداشت آزمایشی."
) -> None:
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    target = vault / "12_Content" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"---\n{head}\n---\n\n{body}\n", encoding="utf-8", newline="\n")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    init_vault(tmp_path)
    return tmp_path


async def _person(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


# ── انتشار ──────────────────────────────────────────────────────────────
async def test_publish_is_idempotent_and_reports_each_change(db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(vault, "a.md", {"title": "مقالهٔ نخست آزمایشی", "status": "published", "slug": "one"})
    _write(vault, "b.md", {"title": "پیش‌نویس دوم آزمایشی", "slug": "two"})

    first = await publish_vault(db_session, vault)
    assert sorted(first.created) == ["12_Content/a.md", "12_Content/b.md"]
    assert first.ok

    second = await publish_vault(db_session, vault)
    assert second.created == [] and second.updated == []
    assert len(second.unchanged) == 2

    _write(vault, "a.md", {"title": "مقالهٔ نخست ویرایش‌شده", "status": "published", "slug": "one"})
    third = await publish_vault(db_session, vault)
    assert third.updated == ["12_Content/a.md"]
    assert third.unchanged == ["12_Content/b.md"]


async def test_only_published_notes_are_reachable(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(vault, "pub.md", {"title": "منتشرشدهٔ آزمایشی", "status": "published", "slug": "pub-x"})
    _write(vault, "draft.md", {"title": "پیش‌نویس آزمایشی", "status": "draft", "slug": "draft-x"})
    await publish_vault(db_session, vault)

    listing = await client.get("/api/v1/public/content")
    assert listing.status_code == 200, listing.text
    slugs = [i["slug"] for i in listing.json()["items"]]
    assert "pub-x" in slugs and "draft-x" not in slugs

    assert (await client.get("/api/v1/public/content/pub-x")).status_code == 200
    assert (await client.get("/api/v1/public/content/draft-x")).status_code == 404


async def test_a_broken_note_does_not_block_the_others(db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(vault, "ok.md", {"title": "یادداشت سالم آزمایشی", "status": "published", "slug": "ok-x"})
    _write(vault, "bad.md", {"title": "یادداشت خراب آزمایشی", "kind": "podcast"})

    report = await publish_vault(db_session, vault)
    assert report.created == ["12_Content/ok.md"]
    assert "kind" in report.errors["12_Content/bad.md"]
    assert not report.ok


async def test_duplicate_slug_is_rejected_for_the_second_note(db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(vault, "a.md", {"title": "نخستین آزمایشی", "status": "published", "slug": "same"})
    _write(vault, "b.md", {"title": "دومین آزمایشی", "status": "published", "slug": "same"})

    report = await publish_vault(db_session, vault)
    assert report.created == ["12_Content/a.md"]
    assert "same" in report.errors["12_Content/b.md"]


async def test_a_vanished_file_is_archived_not_deleted(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(
        vault, "gone.md", {"title": "ناپدیدشونده آزمایشی", "status": "published", "slug": "gone-x"}
    )
    await publish_vault(db_session, vault)
    (vault / "12_Content" / "gone.md").unlink()

    report = await publish_vault(db_session, vault)
    assert report.archived == ["12_Content/gone.md"]
    row = await db_session.scalar(select(ContentItem).where(ContentItem.slug == "gone-x"))
    assert row is not None and row.status == "ARCHIVED"
    assert (await client.get("/api/v1/public/content/gone-x")).status_code == 404

    # فایل برگردد، همان ردیف زنده می‌شود.
    _write(
        vault, "gone.md", {"title": "ناپدیدشونده آزمایشی", "status": "published", "slug": "gone-x"}
    )
    back = await publish_vault(db_session, vault)
    assert back.updated == ["12_Content/gone.md"]
    assert (await client.get("/api/v1/public/content/gone-x")).status_code == 200


async def test_missing_content_folder_archives_nothing(db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    """Vault جابه‌جا یا دیسک وصل نیست ⇒ نباید کل سایت خالی شود."""
    _write(vault, "keep.md", {"title": "ماندنی آزمایشی", "status": "published", "slug": "keep-x"})
    await publish_vault(db_session, vault)

    empty = vault.parent / "empty-vault"
    empty.mkdir(exist_ok=True)
    report = await publish_vault(db_session, empty)
    assert report.archived == []
    assert not report.ok
    row = await db_session.scalar(select(ContentItem).where(ContentItem.slug == "keep-x"))
    assert row is not None and row.status == "PUBLISHED"


# ── دسترسی ─────────────────────────────────────────────────────────────
async def test_access_tiers_gate_the_body(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    for slug, access in (
        ("g-public", "public"),
        ("g-registered", "registered"),
        ("g-student", "student"),
        ("g-premium", "premium"),
    ):
        _write(
            vault,
            f"{slug}.md",
            {
                "title": f"دسترسی {access} آزمایشی",
                "summary": "خلاصهٔ عمومی و بی‌خطر",
                "status": "published",
                "access": access,
                "slug": slug,
            },
            body=f"رازِ-{access}-فقط-برای-مجاز",
        )
    await publish_vault(db_session, vault)

    def body(resp: Any) -> Any:
        assert resp.status_code == 200, resp.text
        return resp.json()["body_md"]

    # ناشناس: فقط عمومی
    assert body(await client.get("/api/v1/public/content/g-public")) is not None
    for slug in ("g-registered", "g-student", "g-premium"):
        detail = await client.get(f"/api/v1/public/content/{slug}")
        assert detail.json()["locked"] is True and detail.json()["body_md"] is None
        assert "رازِ" not in detail.text  # متن، حتی در «مرتبط‌ها»، بیرون نمی‌آید
    assert "رازِ" not in (await client.get("/api/v1/public/content")).text

    # کاربر واردشده (ثبت‌نام = نقش STUDENT، PRD §6.1): عمومی، حساب رایگان و دانشجویان؛ نه «ویژه».
    token, _ = await _person(client, STUDENT, "دانشجو")
    assert body(await client.get("/api/v1/public/content/g-registered", headers=auth(token)))
    assert body(await client.get("/api/v1/public/content/g-student", headers=auth(token)))
    assert (await client.get("/api/v1/public/content/g-premium", headers=auth(token))).json()[
        "locked"
    ]

    # کادر: همه‌چیز.
    staff_token, staff_id = await _person(client, STAFF, "کادر")
    await grant_role(db_session, staff_id, "COORDINATOR")
    assert body(await client.get("/api/v1/public/content/g-premium", headers=auth(staff_token)))

    # فهرست، قفل را برای بیننده درست علامت می‌زند و کش بیننده‌ٔ واردشده خصوصی است.
    anon = await client.get("/api/v1/public/content")
    assert anon.headers["cache-control"] == "public, max-age=60"
    locked_by_slug = {i["slug"]: i["locked"] for i in anon.json()["items"]}
    assert locked_by_slug["g-public"] is False and locked_by_slug["g-premium"] is True
    signed = await client.get("/api/v1/public/content", headers=auth(staff_token))
    assert signed.headers["cache-control"] == "private, no-store"


async def test_filters_search_and_facets(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _write(
        vault,
        "k1.md",
        {
            "title": "مدل جاذبه در توزیع سفر",
            "status": "published",
            "kind": "article",
            "slug": "k1",
            "topics": "[توزیع سفر, حمل‌ونقل]",
        },
    )
    _write(
        vault,
        "k2.md",
        {
            "title": "خلاصهٔ کتاب ایمنی راه",
            "status": "published",
            "kind": "book-summary",
            "slug": "k2",
            "topics": "[ایمنی راه]",
        },
    )
    await publish_vault(db_session, vault)

    books = (await client.get("/api/v1/public/content?kind=BOOK_SUMMARY")).json()
    assert [i["slug"] for i in books["items"]] == ["k2"]

    by_topic = (await client.get("/api/v1/public/content?topic=توزیع سفر")).json()
    assert [i["slug"] for i in by_topic["items"]] == ["k1"]

    found = (await client.get("/api/v1/public/content?q=جاذبه")).json()
    assert [i["slug"] for i in found["items"]] == ["k1"]

    facets = (await client.get("/api/v1/public/content")).json()
    assert {k["value"] for k in facets["kinds"]} >= {"ARTICLE", "BOOK_SUMMARY"}
    assert {t["value"] for t in facets["topics"]} >= {"توزیع سفر", "ایمنی راه"}


# ── پیام گروهی ─────────────────────────────────────────────────────────
async def _student(client: Any, db_session: Any, mobile: str) -> tuple[str, str]:
    token, user_id = await _person(client, mobile, "دانشجوی")
    await grant_role(db_session, user_id, "STUDENT")
    return token, user_id


def _message(vault: Path, audience: str, title: str = "یادآوری آزمایشی") -> Path:
    path = vault / "14_AI/broadcasts/m.md"
    path.write_text(
        f"---\ntitle: {title}\naudience: {audience}\n---\n\nآزمون فردا ساعت ۱۰ است.\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


async def test_broadcast_preview_writes_nothing_and_send_is_idempotent(
    client, db_session, vault: Path
) -> None:  # type: ignore[no-untyped-def]
    token, _ = await _student(client, db_session, STUDENT)
    message = bcast.load_broadcast(_message(vault, f"user:{STUDENT}"))

    preview = await bcast.run_broadcast(db_session, message, send=False)
    assert preview.recipients == 1 and preview.created == 0
    feed = await client.get("/api/v1/notifications", headers=auth(token))
    assert all(n["kind"] != "OWNER_BROADCAST" for n in feed.json()["items"])

    sent = await bcast.run_broadcast(db_session, message, send=True)
    assert sent.created == 1 and sent.already_received == 0
    again = await bcast.run_broadcast(db_session, message, send=True)
    assert again.created == 0 and again.already_received == 1  # اجرای دوباره پیام دوم نمی‌سازد

    feed = await client.get("/api/v1/notifications", headers=auth(token))
    received = [n for n in feed.json()["items"] if n["kind"] == "OWNER_BROADCAST"]
    assert len(received) == 1
    assert received[0]["title"] == "یادآوری آزمایشی"
    assert "آزمون فردا" in received[0]["body"]

    # متن عوض شود، پیام تازه‌ای است.
    changed = bcast.load_broadcast(_message(vault, f"user:{STUDENT}", title="یادآوری دوم آزمایشی"))
    assert (await bcast.run_broadcast(db_session, changed, send=True)).created == 1


async def test_audience_skips_suspended_accounts(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import update

    from silp.models.identity import User

    _, student_id = await _student(client, db_session, STUDENT)
    _, other_id = await _person(client, OUTSIDER, "معلق")
    await db_session.execute(
        update(User).where(User.id == uuid.UUID(other_id)).values(status="SUSPENDED")
    )

    for audience in ("students", "all"):
        ids = await bcast.resolve_audience(db_session, audience)
        assert uuid.UUID(student_id) in ids
        assert uuid.UUID(other_id) not in ids
    assert await bcast.resolve_audience(db_session, f"user:{OUTSIDER}") == []


def test_broadcast_file_validation(vault: Path) -> None:
    from silp.vault.notes import NoteError

    for audience in ("everybody", "user:123", "offering:abc"):
        with pytest.raises(NoteError):
            bcast.load_broadcast(_message(vault, audience))
    with pytest.raises(NoteError):
        bcast.load_broadcast(vault / "14_AI/broadcasts/missing.md")


# ── آینهٔ داده ─────────────────────────────────────────────────────────
async def test_export_mirrors_students_without_national_id(client, db_session, vault: Path) -> None:  # type: ignore[no-untyped-def]
    _, user_id = await _student(client, db_session, STUDENT)

    report = await export_vault(db_session, vault)
    assert report.written
    student_files = list((vault / "02_Students").glob("*.md"))
    assert student_files, report.written
    text = "\n".join(p.read_text(encoding="utf-8") for p in student_files)
    assert "generated: true" in text
    assert user_id in text
    assert STUDENT in text
    assert "national" not in text.lower()
    assert (vault / "DASHBOARD.md").is_file()

    # اجرای دوم بدون تغییر داده، فایلی بازنویسی نمی‌کند.
    again = await export_vault(db_session, vault, only=("students",))
    assert again.written == []


# ── پایداری: دستور CLI واقعاً commit می‌کند ────────────────────────────
async def test_cli_apply_persists_and_preview_does_not(vault: Path, committing_session) -> None:  # type: ignore[no-untyped-def]
    # `committing_session` فقط برای پایان‌کار است: دستور CLI موتور و Redis سراسری را
    # با حلقهٔ همین تست می‌سازد و فیکسچر در پایان آن‌ها را می‌بندد؛ وگرنه تست بعدی
    # با «Event loop is closed» می‌شکند.
    from silp.db.session import get_session_factory
    from silp.scripts import vault as cli

    slug = SLUG
    _write(vault, "cli.md", {"title": "انتشار از خط فرمان", "status": "published", "slug": slug})

    async def stored() -> ContentItem | None:
        async with get_session_factory()() as verifier:  # اتصال جدا: فقط دادهٔ commit‌شده
            return await verifier.scalar(select(ContentItem).where(ContentItem.slug == slug))

    try:
        assert await cli.main(["--vault", str(vault), "publish"]) == 0
        assert await stored() is None, "پیش‌نمایش نباید چیزی بنویسد"

        assert await cli.main(["--vault", str(vault), "publish", "--apply"]) == 0
        row = await stored()
        assert row is not None and row.status == "PUBLISHED", "commit انجام نشده است"
    finally:
        async with get_session_factory()() as cleaner:
            await cleaner.execute(delete(ContentItem).where(ContentItem.slug == slug))
            await cleaner.commit()
