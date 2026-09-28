"""تحلیل یادداشت‌های Vault — بدون دیتابیس (ADR-0030)."""

from __future__ import annotations

import pytest

from silp.vault.notes import NoteError, parse_note, slugify, summarize

FULL = """---
title: چرا مدل چهارمرحله‌ای هنوز زنده است؟
kind: book-summary
status: published
access: registered
topics: [برنامه‌ریزی حمل‌ونقل, تولید سفر]
skills: مدل چهارمرحله‌ای، GIS
course: Transportation Planning
date: 2026-09-28
cover: research
slug: four-step
---

بند اول با **تأکید** و [پیوند](https://example.org) است.

## سرتیتر

متن دوم با [[یادداشت دیگر|نمایش]] و ![[image.png]] و %%نظر پنهان%% تمام می‌شود.
"""


def test_full_note_maps_every_field() -> None:
    note = parse_note(FULL, source_path="12_Content/a.md")
    assert note.kind == "BOOK_SUMMARY"
    assert note.status == "PUBLISHED"
    assert note.access == "REGISTERED"
    assert note.slug == "four-step"
    assert note.topics == ("برنامه‌ریزی حمل‌ونقل", "تولید سفر")
    assert note.skills == ("مدل چهارمرحله‌ای", "GIS")  # هم کاما، هم «،»
    assert note.course_slug == "Transportation Planning"
    assert note.cover == "research"
    assert note.published_at is not None and note.published_at.year == 2026
    assert note.summary == "بند اول با تأکید و پیوند است."
    assert len(note.sha256) == 64
    assert not note.warnings


def test_obsidian_syntax_is_flattened() -> None:
    note = parse_note(FULL, source_path="12_Content/a.md")
    assert "[[" not in note.body_md
    assert "نمایش" in note.body_md
    assert "image.png" not in note.body_md
    assert "نظر پنهان" not in note.body_md


def test_a_note_without_status_is_a_draft() -> None:
    """پیش‌فرض ایمن: چیزی که مالک صریحاً منتشر نکرده، منتشر نمی‌شود."""
    note = parse_note("---\ntitle: فقط یک عنوان\n---\nمتن.", source_path="12_Content/x.md")
    assert note.status == "DRAFT"
    assert note.access == "PUBLIC"
    assert note.kind == "ARTICLE"


def test_title_can_come_from_the_first_heading_and_slug_from_the_filename() -> None:
    note = parse_note("# عنوان از سرتیتر\n\nمتن یادداشت.", source_path="12_Content/my note.md")
    assert note.title_fa == "عنوان از سرتیتر"
    assert note.slug == "my-note"
    assert any("slug" in w for w in note.warnings)


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("---\ntitle: x\n---\nمتن", "عنوان"),
        ("---\ntitle: عنوان خوب\nkind: podcast\n---\nمتن", "kind"),
        ("---\ntitle: عنوان خوب\naccess: vip\n---\nمتن", "access"),
        ("---\ntitle: عنوان خوب\nstatus: live\n---\nمتن", "status"),
        ("---\ntitle: عنوان خوب\n---\n", "خالی"),
        ("---\ntitle: [خراب\n---\nمتن", "YAML"),
        ("---\ntitle: عنوان خوب\ncover: ../etc/passwd\n---\nمتن", "cover"),
        ("---\ntitle: عنوان خوب\ntopics: 5\n---\nمتن", "topics"),
    ],
)
def test_invalid_notes_explain_themselves_in_persian(raw: str, fragment: str) -> None:
    with pytest.raises(NoteError) as excinfo:
        parse_note(raw, source_path="12_Content/x.md")
    assert fragment in str(excinfo.value)


def test_summary_is_capped_and_skips_headings() -> None:
    long = "کلمه " * 200
    result = summarize(f"# تیتر\n\n{long}")
    assert result.endswith("…")
    assert len(result) <= 240


def test_slugify_keeps_persian_and_joins_zwnj() -> None:
    assert slugify("مدل چهارمرحله‌ای  حمل و نقل!") == "مدل-چهارمرحله-ای-حمل-و-نقل"


def test_hash_changes_with_content() -> None:
    a = parse_note("---\ntitle: عنوان خوب\n---\nمتن یک", source_path="12_Content/a.md")
    b = parse_note("---\ntitle: عنوان خوب\n---\nمتن دو", source_path="12_Content/a.md")
    assert a.sha256 != b.sha256
