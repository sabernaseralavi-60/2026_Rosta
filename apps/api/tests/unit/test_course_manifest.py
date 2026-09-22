"""مانیفست پوشهٔ درس — ADR-0008.

مهم‌ترین چیزی که اینجا آزموده می‌شود، وعدهٔ محصول است:

> یک فایل تازه در پوشه بینداز، بدون اینکه هیچ‌جا ثبتش کنی — باید دیده شود.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from silp.content.manifest import (
    ManifestError,
    content_files,
    default_manifest,
    infer_kind,
    infer_title,
    load_manifest,
    write_manifest,
)

PDF_HEADER = b"%PDF-1.7\n%stub\n"


def make_course(tmp_path: Path, name: str = "Traffic Safety") -> Path:
    directory = tmp_path / name
    directory.mkdir()
    return directory


def add_file(directory: Path, name: str, body: bytes = PDF_HEADER) -> Path:
    path = directory / name
    path.write_bytes(body)
    return path


# ── کشف فایل ───────────────────────────────────────────────────────────
def test_content_files_ignores_manifest_and_temp_files(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    (directory / "course.yml").write_text("code: X", encoding="utf-8")
    add_file(directory, "~$draft.docx")
    add_file(directory, "notes.xyz")  # پسوند ناشناخته

    names = [p.name for p in content_files(directory)]
    assert names == ["book.pdf"]


def test_content_files_walks_subdirectories(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    (directory / "week-03").mkdir()
    add_file(directory / "week-03", "slides.pdf")
    assert [p.name for p in content_files(directory)] == ["slides.pdf"]


# ── حدس نوع و عنوان ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("سوال چهارگزینه ایmtp .docx", "QUESTION_BANK"),
        ("پادکست کتاب دیتای ایمنی ترافیک 2025.pdf", "PODCAST"),
        ("Machine learning essentials_FA+++.pdf", "BOOK"),
        ("جزوه هفته ۵.pdf", "NOTE"),
        ("lecture-01.pptx", "SLIDE"),
        ("crashes.csv", "DATASET"),
        ("intro.mp4", "VIDEO"),
        ("plain.pdf", "NOTE"),
    ],
)
def test_infer_kind_reads_the_filename(filename: str, expected: str) -> None:
    """نام فایل حرف کاربر است و به آن گوش داده می‌شود."""
    assert infer_kind(Path(filename)) == expected


def test_infer_title_cleans_separators() -> None:
    assert infer_title(Path("Machine learning essentials_FA+++.pdf")) == (
        "Machine learning essentials FA"
    )


# ── مانیفست پیش‌فرض ────────────────────────────────────────────────────
def test_default_manifest_derives_code_and_slug(tmp_path: Path) -> None:
    manifest = default_manifest(make_course(tmp_path, "Traffic Safety"))
    assert manifest.slug == "traffic-safety"
    assert manifest.code == "TRAFFIC_SAFETY"
    assert manifest.source_dir == "Traffic Safety"


def test_manifestless_folder_still_yields_materials(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    add_file(directory, "podcast خلاصه.pdf")

    manifest = load_manifest(directory)
    assert {m.file for m in manifest.materials} == {"book.pdf", "podcast خلاصه.pdf"}
    assert all(m.access_tier == "SUBSCRIBER" for m in manifest.materials)


# ── وعدهٔ اصلی: فایل تازه بدون ویرایش مانیفست ──────────────────────────
def test_new_file_is_picked_up_without_touching_the_manifest(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    write_manifest(load_manifest(directory))

    add_file(directory, "کتاب تازه.pdf")
    manifest = load_manifest(directory)

    assert {m.file for m in manifest.materials} == {"book.pdf", "کتاب تازه.pdf"}


def test_manifest_entry_overrides_the_guess(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    (directory / "course.yml").write_text(
        "code: RS\n"
        "slug: road-safety\n"
        "title_fa: ایمنی راه\n"
        "materials:\n"
        "  - file: book.pdf\n"
        "    kind: BOOK\n"
        "    title_fa: کتاب ایمنی راه\n"
        "    access_tier: PUBLIC\n"
        "    weeks: [1, 2]\n",
        encoding="utf-8",
    )
    manifest = load_manifest(directory)
    entry = manifest.material_for("book.pdf")

    assert entry is not None
    assert entry.kind == "BOOK"  # حدس «NOTE» بود
    assert entry.title_fa == "کتاب ایمنی راه"
    assert entry.access_tier == "PUBLIC"
    assert entry.weeks == [1, 2]


def test_default_access_tier_flows_to_inferred_materials(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    (directory / "course.yml").write_text(
        "code: RS\nslug: road-safety\ntitle_fa: ایمنی راه\ndefault_access_tier: PUBLIC\n",
        encoding="utf-8",
    )
    manifest = load_manifest(directory)
    assert manifest.materials[0].access_tier == "PUBLIC"


# ── رفت‌وبرگشت ─────────────────────────────────────────────────────────
def test_write_then_load_keeps_everything(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    add_file(directory, "book.pdf")
    original = load_manifest(directory)
    original.materials[0].weeks = [3, 4]
    original.materials[0].section = "فصل ۲"
    original.title_fa = "ایمنی راه"
    write_manifest(original)

    reloaded = load_manifest(directory)
    assert reloaded.title_fa == "ایمنی راه"
    assert reloaded.materials[0].weeks == [3, 4]
    assert reloaded.materials[0].section == "فصل ۲"
    assert len(reloaded.materials) == 1  # نه دو ردیف برای یک فایل


def test_syllabus_is_sorted_by_week(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    (directory / "course.yml").write_text(
        "code: RS\nslug: rs\ntitle_fa: ایمنی\n"
        "syllabus:\n  - week: 3\n    title_fa: سوم\n  - week: 1\n    title_fa: اول\n",
        encoding="utf-8",
    )
    manifest = load_manifest(directory)
    assert [w.week for w in manifest.syllabus] == [1, 3]


# ── خطاها ──────────────────────────────────────────────────────────────
def test_material_without_file_key_is_rejected(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    (directory / "course.yml").write_text(
        "code: RS\nslug: rs\ntitle_fa: ایمنی\nmaterials:\n  - kind: BOOK\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="file"):
        load_manifest(directory)


def test_broken_yaml_is_reported_with_the_path(tmp_path: Path) -> None:
    directory = make_course(tmp_path)
    (directory / "course.yml").write_text("code: [unclosed\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="course.yml"):
        load_manifest(directory)
