"""آزمایشگاه شهر هوشمند — M7-09، FR-CITY-01، §7.9، ADR-0016.

مسیر اصلی: الگوی عمومی ← پروژهٔ C با هشت مرحلهٔ ثابت ← قفل ترتیبی ←
تحویل ناقص (۴۲۲ با همهٔ کمبودها) ← محدوده با مساحت و هم‌پوشانی ← نسخهٔ
فایل مدل در کتابخانه ← نگهبان شواهد تصویری ← کامل شدن و نشان «شهرساز».
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, update
from tests.integration.helpers import (
    auth,
    complete_profile,
    grant_role,
    invalidate,
    login,
    me,
    taxonomy_ids,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TEACHER = "09121660001"
STUDENT = "09121660002"
OUTSIDER = "09121660003"
OTHER_TEACHER = "09121660004"

SUMMARY = "خلاصهٔ تحویل این مرحله با جزئیات کافی برای بازبین پروژه."
KERMAN = [[57.07, 30.28], [57.08, 30.28], [57.08, 30.29], [57.07, 30.29], [57.07, 30.28]]
OSM_BYTES = b'<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6"></osm>\n'
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


async def _actor(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


async def _teacher(client: Any, db_session: Any, mobile: str = TEACHER) -> tuple[str, str]:
    token, user_id = await _actor(client, mobile, "صابر")
    await grant_role(db_session, user_id, "INSTRUCTOR")
    return token, user_id


async def _city_payload(client: Any, **overrides: Any) -> dict[str, Any]:
    skills = await taxonomy_ids(client, "skills", limit=1)
    payload: dict[str, Any] = {
        "title_fa": "مدل‌سازی SUMO محور جمهوری کرمان",
        "summary": "مدل ریزنگر ترافیکی محور و سناریوهای بهبود برای شهرداری.",
        "description": "پروژهٔ نمونهٔ گردش‌کار هشت‌مرحله‌ای آزمایشگاه شهر هوشمند.",
        "kind": "C_PROBLEM",
        "expected_output": "مدل معتبر SUMO، گزارش مدیریتی و داشبورد",
        "team_size_min": 1,
        "team_size_max": 4,
        "work_style": "TEAM",
        "starts_on": "2026-10-01",
        "required_skills": [{"skill_id": skills[0], "min_level": 2}],
        "workflow": "CITY",
    }
    payload.update(overrides)
    return payload


async def _running_city(client: Any, db_session: Any) -> dict[str, Any]:
    """پروژهٔ شهری در جریان با استاد (مدیر) و یک دانشجو."""
    teacher_token, teacher_id = await _teacher(client, db_session)
    student_token, student_id = await _actor(client, STUDENT, "مینا")
    created = await client.post(
        "/api/v1/projects", headers=auth(teacher_token), json=await _city_payload(client)
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/projects/{project_id}/publish", headers=auth(teacher_token)
    )
    assert response.status_code == 200, response.text
    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "به مدل‌سازی ترافیک و SUMO علاقه دارم و وقت کافی دارم."},
    )
    assert applied.status_code == 201, applied.text
    decided = await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(teacher_token),
        json={"decision": "ACCEPTED"},
    )
    assert decided.status_code == 200, decided.text
    await invalidate(student_id)
    started = await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(teacher_token))
    assert started.status_code == 200, started.text
    board = await _board(client, teacher_token, project_id)
    return {
        "teacher": teacher_token,
        "teacher_id": teacher_id,
        "student": student_token,
        "student_id": student_id,
        "project_id": project_id,
        "stages": {s["number"]: s["milestone"]["id"] for s in board["stages"]},
    }


async def _board(client: Any, token: str, project_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/projects/{project_id}/city", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _upload(client: Any, storage: Any, token: str, name: str, ctype: str, body: bytes) -> str:
    reserved = await client.post(
        "/api/v1/files/upload-url",
        headers=auth(token),
        json={
            "original_name": name,
            "content_type": ctype,
            "size_bytes": len(body),
            "purpose": "DELIVERABLE",
        },
    )
    assert reserved.status_code == 200, reserved.text
    payload = reserved.json()
    key = payload["upload_url"].split("/", 3)[-1]
    storage.put_object(key, body, payload["headers"]["Content-Type"])
    completed = await client.post(
        f"/api/v1/files/{payload['file_id']}/complete", headers=auth(token)
    )
    assert completed.status_code == 200, completed.text
    return str(payload["file_id"])


async def _approve_through(db_session: Any, project_id: str, last: int) -> None:
    """مراحل ۱ تا `last` را مستقیم تأییدشده می‌کند — برای آزمون مراحل بعدی."""
    from silp.models.delivery import Milestone

    await db_session.execute(
        update(Milestone)
        .where(Milestone.project_id == project_id, Milestone.workflow_stage <= last)
        .values(status="APPROVED", approved_at=datetime.now(UTC))
    )
    await db_session.flush()


async def _submit(client: Any, token: str, milestone_id: str, **body: Any) -> Any:
    return await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables", headers=auth(token), json=body
    )


async def _review(client: Any, token: str, deliverable_id: str, decision: str, **body: Any) -> Any:
    return await client.post(
        f"/api/v1/deliverables/{deliverable_id}/review",
        headers=auth(token),
        json={"decision": decision, **body},
    )


async def _kinds(db_session: Any, user_id: str) -> list[str]:
    from silp.models.messaging import Notification

    rows = await db_session.scalars(
        select(Notification.kind).where(Notification.user_id == user_id)
    )
    return list(rows)


def _area_body(**evidence: Any) -> dict[str, Any]:
    return {
        "body": SUMMARY,
        "evidence": {
            "area": {"type": "Polygon", "coordinates": [KERMAN]},
            "justification": "محور جمهوری بیشترین صف و شکایت را در گزارش شهرداری کرمان دارد.",
            **evidence,
        },
    }


# ── الگو ───────────────────────────────────────────────────────────────
async def test_template_is_public_and_complete(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/city/workflow")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["number"] for s in body["stages"]] == list(range(1, 9))
    assert body["total_points"] == 500
    verify = body["stages"][2]
    assert verify["structured"] == "CHECKS"
    assert all(item["auto"] for item in verify["checklist"])
    assert {o["code"] for o in body["sources"]} == {"GOOGLE", "NESHAN", "BALAD", "FIELD"}
    sumo = body["stages"][3]
    assert [f["kind"] for f in sumo["files"]] == ["SUMO_NET", "SUMO_ROUTES"]


async def test_city_project_gets_eight_fixed_stages_owned_by_the_lead(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    token, teacher_id = await _teacher(client, db_session)
    created = await client.post(
        "/api/v1/projects", headers=auth(token), json=await _city_payload(client)
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["workflow"] == "CITY"

    milestones = (
        await client.get(f"/api/v1/projects/{project['id']}/milestones", headers=auth(token))
    ).json()
    assert [m["workflow_stage"] for m in milestones] == list(range(1, 9))
    assert {m["owner_id"] for m in milestones} == {teacher_id}
    assert milestones[0]["due_on"] == "2026-10-08"
    assert sum(m["points"] for m in milestones) == 500

    # نوع دیگر الگو نمی‌گیرد.
    wrong = await client.post(
        "/api/v1/projects",
        headers=auth(token),
        json=await _city_payload(client, kind="B_RESEARCH"),
    )
    assert wrong.status_code == 422, wrong.text

    # مرحلهٔ الگو ثابت است: عنوان نه، مهلت و بارم بله؛ حذف هرگز.
    stage = milestones[1]
    edit = {
        "title_fa": stage["title_fa"],
        "description": "شرح بومی‌شده",
        "sort_order": stage["sort_order"],
        "due_on": "2026-11-01",
        "points": 45,
        "is_required": True,
        "output_kind": stage["output_kind"],
        "checklist": stage["checklist"],
    }
    ok = await client.patch(f"/api/v1/milestones/{stage['id']}", headers=auth(token), json=edit)
    assert ok.status_code == 200, ok.text
    renamed = await client.patch(
        f"/api/v1/milestones/{stage['id']}",
        headers=auth(token),
        json={**edit, "title_fa": "نام دلخواه"},
    )
    assert renamed.status_code == 409, renamed.text
    deleted = await client.delete(f"/api/v1/milestones/{stage['id']}", headers=auth(token))
    assert deleted.status_code == 409, deleted.text

    # الگو پس از ساخت عوض نمی‌شود.
    patched = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=auth(token),
        json=await _city_payload(client, workflow=None),
    )
    assert patched.status_code == 422, patched.text


# ── قفل ترتیبی و شاهد ──────────────────────────────────────────────────
async def test_stages_unlock_in_order_and_all_gaps_come_back_together(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    ctx = await _running_city(client, db_session)
    student, teacher, stages = ctx["student"], ctx["teacher"], ctx["stages"]

    locked = await _submit(client, student, stages[2], body=SUMMARY)
    assert locked.status_code == 409, locked.text
    assert locked.json()["error"]["code"] == "CITY_STAGE_LOCKED"
    assert locked.json()["error"]["details"]["blocked_by"] == 1

    incomplete = await _submit(client, student, stages[1], body="کوتاه", evidence={})
    assert incomplete.status_code == 422, incomplete.text
    missing = incomplete.json()["error"]["details"]["missing"]
    assert any("خلاصهٔ تحویل" in m for m in missing)
    assert any("توجیه انتخاب محدوده" in m for m in missing)
    assert any("GeoJSON" in m for m in missing)

    # مسئول مرحلهٔ ۲ دانشجوست؛ باز شدنش به او خبر داده می‌شود.
    assigned = await client.put(
        f"/api/v1/milestones/{stages[2]}/owner",
        headers=auth(teacher),
        json={"owner_id": ctx["student_id"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["owner_name"]
    stranger = await client.put(
        f"/api/v1/milestones/{stages[3]}/owner",
        headers=auth(teacher),
        json={"owner_id": ctx["teacher_id"][:-4] + "0000"},
    )
    assert stranger.status_code == 422, stranger.text
    cleared = await client.put(
        f"/api/v1/milestones/{stages[3]}/owner", headers=auth(teacher), json={"owner_id": None}
    )
    assert cleared.status_code == 422, cleared.text

    submitted = await _submit(client, student, stages[1], **_area_body())
    assert submitted.status_code == 201, submitted.text
    evidence = submitted.json()["evidence"]
    assert evidence["area"]["type"] == "MultiPolygon"
    assert 0.9 < evidence["area_km2"] < 1.3
    assert evidence["overlaps"] == []

    approved = await _review(client, teacher, submitted.json()["id"], "APPROVED")
    assert approved.status_code == 200, approved.text

    board = await _board(client, student, ctx["project_id"])
    assert board["current_stage"] == 2
    assert [s["locked"] for s in board["stages"]][:3] == [False, False, True]
    assert board["area"]["approved"] is True
    kinds = await _kinds(db_session, ctx["student_id"])
    assert "MILESTONE_OWNER_ASSIGNED" in kinds
    assert "CITY_STAGE_UNLOCKED" in kinds


async def test_overlapping_areas_are_flagged_not_blocked(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    ctx = await _running_city(client, db_session)
    first = await _submit(client, ctx["student"], ctx["stages"][1], **_area_body())
    assert first.status_code == 201, first.text

    # پروژهٔ شهری دیگری با محدوده‌ای که همان محور را قطع می‌کند.
    other_token, _ = await _teacher(client, db_session, OTHER_TEACHER)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(other_token),
        json=await _city_payload(client, title_fa="تقاطع‌های مرکز کرمان"),
    )
    other_id = created.json()["id"]
    other_stage = (
        await client.get(f"/api/v1/projects/{other_id}/city", headers=auth(other_token))
    ).json()["stages"][0]["milestone"]["id"]
    await client.post(f"/api/v1/projects/{other_id}/publish", headers=auth(other_token))
    shifted = [[lon + 0.005, lat + 0.005] for lon, lat in KERMAN]
    overlapping = await _submit(
        client,
        other_token,
        other_stage,
        body=SUMMARY,
        evidence={
            "area": {"type": "Polygon", "coordinates": [shifted]},
            "justification": "تقاطع‌های پرتصادف مرکز شهر که در گزارش پلیس راه آمده‌اند.",
        },
    )
    assert overlapping.status_code == 201, overlapping.text
    overlaps = overlapping.json()["evidence"]["overlaps"]
    assert [o["project_id"] for o in overlaps] == [ctx["project_id"]]


# ── فایل مدل و کتابخانه ────────────────────────────────────────────────
async def test_model_files_are_versioned_and_the_library_is_shared(  # type: ignore[no-untyped-def]
    client, db_session, storage
) -> None:
    ctx = await _running_city(client, db_session)
    await _approve_through(db_session, ctx["project_id"], 1)
    student, teacher = ctx["student"], ctx["teacher"]
    stage_two = ctx["stages"][2]
    evidence = {
        "node_count": 1840,
        "edge_count": 3920,
        "osm_source": "Geofabrik iran-latest",
        "osm_data_date": "2026-09-01",
        "extracted_on": "2026-09-20",
    }

    first_file = await _upload(
        client, storage, student, "jomhouri.osm", "application/xml", OSM_BYTES
    )
    first = await _submit(
        client, student, stage_two, body=SUMMARY, evidence=evidence, file_ids=[first_file]
    )
    assert first.status_code == 201, first.text
    changes = await _review(
        client,
        teacher,
        first.json()["id"],
        "CHANGES_REQUESTED",
        feedback="برش محدوده را بزرگ‌تر کن.",
    )
    assert changes.status_code == 200, changes.text

    second_file = await _upload(
        client, storage, student, "jomhouri-v2.osm", "application/xml", OSM_BYTES
    )
    second = await _submit(
        client, student, stage_two, body=SUMMARY, evidence=evidence, file_ids=[second_file]
    )
    assert second.status_code == 201, second.text
    approved = await _review(client, teacher, second.json()["id"], "APPROVED")
    assert approved.status_code == 200, approved.text

    library = await client.get(f"/api/v1/projects/{ctx['project_id']}/files", headers=auth(teacher))
    assert library.status_code == 200, library.text
    osm = next(a for a in library.json()["artifacts"] if a["artifact"] == "OSM")
    assert [(v["version"], v["is_current"]) for v in osm["versions"]] == [(2, True), (1, False)]
    assert osm["versions"][1]["deliverable_status"] == "CHANGES_REQUESTED"
    assert len(library.json()["files"]) == 2

    board = await _board(client, teacher, ctx["project_id"])
    summary = next(a for a in board["artifacts"] if a["artifact"] == "OSM")
    assert (summary["current_version"], summary["latest_version"]) == (2, 2)

    # بازبین فایل دانشجو را دانلود می‌کند؛ بیرونی نه، و فایل بیگانه ۴۰۴ است.
    download = await client.get(
        f"/api/v1/projects/{ctx['project_id']}/files/{first_file}/download-url",
        headers=auth(teacher),
    )
    assert download.status_code == 200, download.text
    outsider_token, _ = await _actor(client, OUTSIDER, "رضا")
    denied = await client.get(
        f"/api/v1/projects/{ctx['project_id']}/files/{first_file}/download-url",
        headers=auth(outsider_token),
    )
    assert denied.status_code == 403, denied.text
    stray = await _upload(client, storage, outsider_token, "x.pdf", "application/pdf", PDF_BYTES)
    missing = await client.get(
        f"/api/v1/projects/{ctx['project_id']}/files/{stray}/download-url",
        headers=auth(teacher),
    )
    assert missing.status_code == 404, missing.text

    # پیوست تحویل حذف نمی‌شود — نسخه‌ها هرگز پاک نمی‌شوند (§7.6).
    removed = await client.delete(f"/api/v1/files/{first_file}", headers=auth(student))
    assert removed.status_code == 409, removed.text


async def test_sumo_stage_needs_both_network_and_routes(  # type: ignore[no-untyped-def]
    client, db_session, storage
) -> None:
    ctx = await _running_city(client, db_session)
    await _approve_through(db_session, ctx["project_id"], 3)
    net = await _upload(client, storage, ctx["student"], "a.net.xml", "text/xml", OSM_BYTES)
    response = await _submit(
        client,
        ctx["student"],
        ctx["stages"][4],
        body=SUMMARY,
        evidence={
            "netconvert_errors": 0,
            "traffic_lights": 3,
            "sumo_version": "1.20.0",
            "error_report": "دو هشدار اتصال رفع شد؛ خطایی باقی نماند.",
        },
        checklist_confirmed=[1, 2],
        file_ids=[net],
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"]["missing"] == ["فایل .rou.xml را پیوست کن"]


# ── قاعدهٔ حیاتی مرحلهٔ ۳ ─────────────────────────────────────────────
async def test_verification_is_never_approved_without_images(  # type: ignore[no-untyped-def]
    client, db_session, storage
) -> None:
    from silp.models.delivery import Deliverable

    ctx = await _running_city(client, db_session)
    await _approve_through(db_session, ctx["project_id"], 2)
    student = ctx["student"]
    neshan = await _upload(client, storage, student, "neshan.png", "image/png", PNG_BYTES)
    field = await _upload(client, storage, student, "field.png", "image/png", PNG_BYTES)
    row = {
        "location": "تقاطع جمهوری و شهدا",
        "finding": "جهت خیابان فرعی در OSM دوطرفه است.",
        "verdict": "MISMATCH",
        "severity": "CRITICAL",
        "sources": ["NESHAN", "FIELD"],
        "image_file_ids": [neshan, field],
        "resolution": "جهت یک‌طرفه در داده اصلاح شد.",
    }

    without = await _submit(
        client,
        student,
        ctx["stages"][3],
        body=SUMMARY,
        evidence={"checks": [{**row, "image_file_ids": []}]},
    )
    assert without.status_code == 422, without.text
    assert any("شاهد تصویری" in m for m in without.json()["error"]["details"]["missing"])

    submitted = await _submit(
        client,
        student,
        ctx["stages"][3],
        body=SUMMARY,
        evidence={"checks": [row]},
        file_ids=[neshan, field],
    )
    assert submitted.status_code == 201, submitted.text

    # دفاع در عمق: اگر تصویرها از راه دیگری از شاهد افتاده باشند.
    await db_session.execute(
        update(Deliverable)
        .where(Deliverable.id == submitted.json()["id"])
        .values(evidence={"checks": [{**row, "image_file_ids": []}], "checklist_confirmed": []})
    )
    await db_session.flush()
    db_session.expire_all()
    refused = await _review(client, ctx["teacher"], submitted.json()["id"], "APPROVED")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "CITY_EVIDENCE_MISSING"


# ── کامل شدن و «شهرساز» ────────────────────────────────────────────────
async def test_last_approval_completes_the_workflow_and_earns_city_builder(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    from silp.models.project import Project
    from silp.services.badge_service import BadgeService

    ctx = await _running_city(client, db_session)
    await _approve_through(db_session, ctx["project_id"], 7)
    submitted = await _submit(
        client,
        ctx["student"],
        ctx["stages"][8],
        body=SUMMARY,
        links=["https://example.org/guide"],
        evidence={
            "dashboard_url": "https://dashboard.example.org/kerman",
            "update_method": "هر ماه فایل شمارش شهرداری در پوشهٔ داده جایگزین می‌شود.",
        },
        checklist_confirmed=[0, 1, 2],
    )
    assert submitted.status_code == 201, submitted.text
    reviewed = await _review(client, ctx["teacher"], submitted.json()["id"], "APPROVED")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["workflow_completed"] is True

    project = await db_session.get(Project, ctx["project_id"])
    await db_session.refresh(project)
    assert project.workflow_completed_at is not None
    assert "CITY_WORKFLOW_COMPLETED" in await _kinds(db_session, ctx["student_id"])

    badges = BadgeService(db_session)
    assert "CITY_BUILDER" in await badges.evaluate_user(ctx["student_id"])
    # مدیری که فقط بررسی کرد، شهرساز نیست.
    assert "CITY_BUILDER" not in await badges.evaluate_user(ctx["teacher_id"])

    listing = await client.get("/api/v1/city/projects")
    mine = next(p for p in listing.json() if p["project"]["id"] == ctx["project_id"])
    assert mine["current_stage"] is None and mine["approved_count"] == 8


async def test_leaving_member_hands_ownership_back_to_the_lead(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    ctx = await _running_city(client, db_session)
    await client.put(
        f"/api/v1/milestones/{ctx['stages'][4]}/owner",
        headers=auth(ctx["teacher"]),
        json={"owner_id": ctx["student_id"]},
    )
    left = await client.post(
        f"/api/v1/projects/{ctx['project_id']}/leave",
        headers=auth(ctx["student"]),
        json={"reason": "تداخل با کارآموزی"},
    )
    assert left.status_code in (200, 204), left.text
    board = await _board(client, ctx["teacher"], ctx["project_id"])
    assert board["stages"][3]["milestone"]["owner_id"] == ctx["teacher_id"]
