"""آزمایشگاه شهر هوشمند — منطق خالص الگو، شاهد و محدوده (ADR-0016)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from silp.domain import city
from silp.domain.city import AttachedFile

TODAY = date(2026, 9, 23)

# محدوده‌ای حدود ۱٫۱ × ۱٫۱ کیلومتر در مرکز کرمان — ۰٫۰۱ درجه در هر ضلع.
KERMAN = [[57.07, 30.28], [57.08, 30.28], [57.08, 30.29], [57.07, 30.29], [57.07, 30.28]]
POLYGON = {"type": "Polygon", "coordinates": [KERMAN]}

PNG_A = AttachedFile("a", "neshan.png", "image/png")
PNG_B = AttachedFile("b", "field.jpg", "image/jpeg")
SUMMARY = "خلاصهٔ تحویل این مرحله با جزئیات کافی برای بازبین پروژه."


def _submit(number: int, **overrides: Any) -> tuple[dict[str, Any], list[str]]:
    kwargs: dict[str, Any] = {
        "body": SUMMARY,
        "links": [],
        "files": [],
        "evidence": {},
        "checklist_confirmed": list(range(len(city.stage(number).checklist))),
        "today": TODAY,
    }
    kwargs.update(overrides)
    return city.validate_submission(number, **kwargs)


# ── الگو ───────────────────────────────────────────────────────────────
def test_template_has_eight_ordered_stages_worth_the_project_reward() -> None:
    assert [s.number for s in city.STAGES] == list(range(1, 9))
    assert [s.title_fa for s in city.STAGES] == [
        "انتخاب محدوده",
        "استخراج OSM",
        "راستی‌آزمایی",
        "مدل SUMO",
        "تخمین تقاضا",
        "سناریوسازی",
        "گزارش مدیریتی",
        "داشبورد شهرداری",
    ]
    # §14.5 P-02 — «۵۰۰ امتیاز»، و یک نیم‌سال (۱۶ هفته).
    assert city.TOTAL_POINTS == 500
    assert city.TOTAL_DAYS == 16 * 7
    assert all(s.checklist for s in city.STAGES)


def test_due_dates_accumulate_from_the_start_date() -> None:
    dues = city.due_dates(date(2026, 10, 1))
    assert dues[1] == date(2026, 10, 8)
    assert dues[8] == date(2026, 10, 1) + timedelta(days=112)
    assert all(v is None for v in city.due_dates(None).values())


def test_stage_opens_only_after_the_previous_is_approved() -> None:
    assert not city.is_locked(1, {})
    assert city.is_locked(2, {1: "SUBMITTED"})
    assert not city.is_locked(2, {1: "APPROVED"})
    assert city.current_stage({1: "APPROVED", 2: "IN_PROGRESS"}) == 2
    assert city.current_stage({n: "APPROVED" for n in range(1, 9)}) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("kerman.osm", "OSM"),
        ("Kerman.OSM.XML", "OSM"),
        ("corridor.net.xml", "SUMO_NET"),
        ("peak.rou.xml", "SUMO_ROUTES"),
        ("config.sumocfg", None),
        ("notes.xml", None),
    ],
)
def test_artifact_is_read_from_the_file_name(name: str, expected: str | None) -> None:
    assert city.artifact_of(name) == expected


# ── محدوده ─────────────────────────────────────────────────────────────
def test_area_is_computed_on_the_sphere() -> None:
    polygons, problems = city.parse_area(POLYGON)
    assert problems == []
    # ۰٫۰۱° عرض ≈ ۱٫۱۱ کیلومتر، ۰٫۰۱° طول در عرض ۳۰٫۳ ≈ ۰٫۹۶ کیلومتر.
    assert city.area_km2(polygons) == pytest.approx(1.07, rel=0.03)


def test_feature_collections_are_unwrapped() -> None:
    wrapped = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": POLYGON}],
    }
    polygons, problems = city.parse_area(wrapped)
    assert problems == [] and len(polygons) == 1


@pytest.mark.parametrize(
    ("geometry", "fragment"),
    [
        ({"type": "Polygon", "coordinates": [KERMAN[:-1]]}, "بسته نیست"),
        ({"type": "Point", "coordinates": [57.07, 30.28]}, "چندضلعی"),
        ({"type": "Polygon", "coordinates": [[["a", 1], [2, 3]]]}, "عددی"),
        (
            {"type": "Polygon", "coordinates": [[[200, 30], [201, 30], [201, 31], [200, 30]]]},
            "بازهٔ",
        ),
        ("not geojson", "GeoJSON"),
    ],
)
def test_broken_areas_say_what_is_wrong(geometry: Any, fragment: str) -> None:
    _, problems = city.parse_area(geometry)
    assert any(fragment in p for p in problems), problems


def test_area_outside_the_allowed_range_is_rejected() -> None:
    tiny = [[57.07, 30.28], [57.0701, 30.28], [57.0701, 30.2801], [57.07, 30.28]]
    _, problems = _submit(
        1,
        evidence={"area": {"type": "Polygon", "coordinates": [tiny]}, "justification": "ا" * 60},
    )
    assert any("مساحت محدوده" in p for p in problems)


def test_overlap_detects_crossing_and_containment_but_not_neighbours() -> None:
    mine = city.parse_area(POLYGON)[0]
    crossing = city.parse_area(
        {
            "type": "Polygon",
            "coordinates": [
                [[57.075, 30.285], [57.09, 30.285], [57.09, 30.3], [57.075, 30.3], [57.075, 30.285]]
            ],
        }
    )[0]
    inside = city.parse_area(
        {
            "type": "Polygon",
            "coordinates": [
                [[57.072, 30.282], [57.074, 30.282], [57.074, 30.284], [57.072, 30.282]]
            ],
        }
    )[0]
    apart = city.parse_area(
        {
            "type": "Polygon",
            "coordinates": [[[57.1, 30.3], [57.11, 30.3], [57.11, 30.31], [57.1, 30.3]]],
        }
    )[0]
    assert city.polygons_overlap(mine, crossing)
    assert city.polygons_overlap(mine, inside)
    assert city.polygons_overlap(inside, mine)
    assert not city.polygons_overlap(mine, apart)


def test_stage_one_stores_a_normalized_multipolygon() -> None:
    cleaned, problems = _submit(
        1, evidence={"area": POLYGON, "justification": "محور اصلی کرمان " * 5}
    )
    assert problems == []
    assert cleaned["area"]["type"] == "MultiPolygon"
    assert cleaned["area_km2"] == pytest.approx(1.07, rel=0.03)
    assert len(cleaned["bbox"]) == 4


# ── شاهد عمومی ─────────────────────────────────────────────────────────
def test_all_problems_come_back_together() -> None:
    _, problems = _submit(2, body="کوتاه", evidence={"node_count": 0}, checklist_confirmed=[])
    joined = " | ".join(problems)
    assert "خلاصهٔ تحویل" in joined
    assert "تعداد گره‌ها" in joined
    assert "تعداد یال‌ها" in joined
    assert "فایل .osm" in joined
    # چک‌لیست مرحلهٔ ۲ همه خودکار است؛ تیک لازم ندارد.
    assert "چک‌لیست" not in joined


def test_osm_stage_needs_exactly_one_xml_osm_file() -> None:
    evidence = {
        "node_count": 1200,
        "edge_count": 2600,
        "osm_source": "Geofabrik iran-latest",
        "osm_data_date": "2026-09-01",
        "extracted_on": "2026-09-20",
    }
    osm = AttachedFile("o", "kerman.osm", "application/xml")
    assert _submit(2, evidence=evidence, files=[osm])[1] == []
    wrong_type = AttachedFile("o", "kerman.osm", "application/pdf")
    assert any("فایل .osm" in p for p in _submit(2, evidence=evidence, files=[wrong_type])[1])
    twice = [osm, AttachedFile("p", "other.osm", "text/xml")]
    assert any("فقط یک" in p for p in _submit(2, evidence=evidence, files=twice)[1])


def test_future_dates_and_non_zero_netconvert_errors_are_rejected() -> None:
    _, problems = _submit(
        2,
        evidence={
            "node_count": 1,
            "edge_count": 1,
            "osm_source": "Overpass",
            "osm_data_date": "2027-01-01",
            "extracted_on": "2026-09-01",
        },
        files=[AttachedFile("o", "a.osm", "application/xml")],
    )
    assert any("آینده" in p for p in problems)

    net = AttachedFile("n", "a.net.xml", "application/xml")
    rou = AttachedFile("r", "a.rou.xml", "text/xml")
    _, problems = _submit(
        4,
        evidence={
            "netconvert_errors": 3,
            "traffic_lights": 4,
            "sumo_version": "1.20.0",
            "error_report": "دو هشدار اتصال رفع شد و یکی باقی ماند.",
        },
        files=[net, rou],
    )
    assert problems == ["«تعداد خطای netconvert» باید ۰ باشد"]


def test_manual_checklist_items_must_be_confirmed() -> None:
    net = AttachedFile("n", "a.net.xml", "application/xml")
    rou = AttachedFile("r", "a.rou.xml", "application/xml")
    evidence = {
        "netconvert_errors": 0,
        "traffic_lights": 4,
        "sumo_version": "1.20.0",
        "error_report": "خروجی netconvert بدون خطا بود.",
    }
    _, problems = _submit(4, evidence=evidence, files=[net, rou], checklist_confirmed=[0])
    assert len(problems) == 1
    assert "اتصال شبکه بررسی شده" in problems[0]
    assert "چراغ‌ها کدگذاری شده‌اند" in problems[0]


def test_unknown_evidence_keys_are_not_silently_dropped() -> None:
    _, problems = _submit(8, evidence={"dashboard_url": "https://x.ir", "extra": 1})
    assert any("شاهد ناشناخته" in p for p in problems)


# ── مرحلهٔ ۳ — قاعدهٔ حیاتی ───────────────────────────────────────────
def _check(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "location": "تقاطع شهدا",
        "finding": "جهت خیابان در OSM دوطرفه ثبت شده است.",
        "verdict": "MISMATCH",
        "severity": "CRITICAL",
        "sources": ["NESHAN", "FIELD"],
        "image_file_ids": ["a", "b"],
        "resolution": "جهت یک‌طرفه در داده اصلاح شد.",
    }
    row.update(overrides)
    return row


def test_verification_with_two_sources_and_images_passes() -> None:
    cleaned, problems = _submit(3, evidence={"checks": [_check()]}, files=[PNG_A, PNG_B])
    assert problems == []
    assert cleaned["checks"][0]["sources"] == ["NESHAN", "FIELD"]
    assert city.image_count(cleaned) == 2


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"image_file_ids": []}, "شاهد تصویری ندارد"),
        ({"sources": ["NESHAN"], "severity": "NORMAL"}, "دو منبع مستقل"),
        ({"sources": ["NESHAN", "BALAD"]}, "بازدید میدانی"),
        ({"resolution": ""}, "اصلاح انجام‌شده"),
        ({"image_file_ids": ["z"]}, "پیوست نشده"),
    ],
)
def test_verification_rules(override: dict[str, Any], fragment: str) -> None:
    _, problems = _submit(3, evidence={"checks": [_check(**override)]}, files=[PNG_A, PNG_B])
    assert any(fragment in p for p in problems), problems


def test_verification_needs_images_not_other_files() -> None:
    pdf = AttachedFile("a", "neshan.pdf", "application/pdf")
    _, problems = _submit(
        3, evidence={"checks": [_check(image_file_ids=["a"])]}, files=[pdf, PNG_B]
    )
    assert any("فایل تصویر" in p for p in problems)


def test_evidence_must_come_from_at_least_two_sources_overall() -> None:
    match = _check(verdict="MATCH", severity="NORMAL", sources=["GOOGLE"], resolution="")
    _, problems = _submit(3, evidence={"checks": [match]}, files=[PNG_A, PNG_B])
    assert problems == ["شواهد باید دست‌کم از دو منبع مختلف باشد"]


def test_empty_verification_table_is_rejected() -> None:
    _, problems = _submit(3, evidence={"checks": []})
    assert any("دست‌کم یک ردیف" in p for p in problems)


# ── مرحلهٔ ۶ ───────────────────────────────────────────────────────────
def _scenario(name: str, *, baseline: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"شرح سناریوی {name} با جزئیات",
        "is_baseline": baseline,
        "delay_s": 42.5,
        "queue_m": 120,
        "emissions_kg": 31.2,
    }


def test_scenarios_need_three_with_exactly_one_baseline() -> None:
    three = [_scenario("پایه", baseline=True), _scenario("چراغ"), _scenario("دوربرگردان")]
    assert _submit(6, evidence={"scenarios": three}, links=["https://x.ir/r"])[1] == []

    _, problems = _submit(6, evidence={"scenarios": three[:2]}, links=["https://x.ir/r"])
    assert any("دست‌کم ۳ سناریو" in p for p in problems)

    no_base = [_scenario("الف"), _scenario("ب"), _scenario("ج")]
    _, problems = _submit(6, evidence={"scenarios": no_base}, links=["https://x.ir/r"])
    assert any("سناریوی پایه" in p for p in problems)

    missing_kpi = [*three[:2], {**_scenario("ج"), "queue_m": None}]
    _, problems = _submit(6, evidence={"scenarios": missing_kpi}, links=["https://x.ir/r"])
    assert any("طول صف" in p for p in problems)


# ── مرحلهٔ ۷ ───────────────────────────────────────────────────────────
def test_report_is_at_most_twenty_pages_with_a_pdf() -> None:
    evidence = {
        "page_count": 24,
        "executive_summary": "خلاصه " * 60,
        "recommendations": "زمان‌بندی چراغ تقاطع شهدا را در ساعت اوج عوض کنید." * 2,
        "cost_estimate_rial": 1_200_000_000,
    }
    _, problems = _submit(7, evidence=evidence, checklist_confirmed=[3, 4])
    assert any("حداکثر ۲۰" in p for p in problems)
    assert any("گزارش PDF" in p for p in problems)
