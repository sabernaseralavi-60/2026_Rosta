"""قواعد خالص فهرست دانشجویان و خواندن اکسل — ADR-0035."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from silp.content.roster_file import normalize_title, read_rosters
from silp.domain.identity import roster as rules

SECRET = "unit-test-secret-unit-test-secret"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("402123456", "402123456"),
        ("۴۰۲۱۲۳۴۵۶", "402123456"),  # ارقام فارسی
        ("٤٠٢١٢٣٤٥٦", "402123456"),  # ارقام عربی-هندی
        (" 4021-234 56 ", "402123456"),
        ("402123456.0", "402123456"),  # اکسل عدد را اعشاری می‌نویسد
        ("1234", None),  # کوتاه
        ("abc123456", None),
        ("", None),
        (None, None),
    ],
)
def test_student_number_normalisation(raw: str | None, expected: str | None) -> None:
    assert rules.normalize_student_no(raw) == expected


def test_digest_is_keyed_stable_and_not_the_number() -> None:
    a = rules.digest("402123456", SECRET)
    assert a == rules.digest("402123456", SECRET)
    assert a != rules.digest("402123456", SECRET + "x")  # کلید عوض شود، هش عوض می‌شود
    assert a != rules.digest("402123457", SECRET)
    assert "402123456" not in a and len(a) == 64


def test_masked_name_hides_the_family_name() -> None:
    assert rules.masked_name("علی", "رضایی") == "علی ر."
    assert rules.masked_name("علی", "") == "علی"


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("abc", "دست‌کم"),
        ("402123456", "شمارهٔ دانشجویی"),
        ("۴۰۲۱۲۳۴۵۶", "شمارهٔ دانشجویی"),
        ("09121234567", "شمارهٔ دانشجویی"),
        ("11111111", "ساده"),
        ("Kerman-1405-safe", None),
    ],
)
def test_password_rules(password: str, problem: str | None) -> None:
    forbidden = {rules.digest("402123456", SECRET), rules.digest("09121234567", SECRET)}
    result = rules.password_problem(password, forbidden_digests=forbidden, secret=SECRET)
    if problem is None:
        assert result is None
    else:
        assert result is not None and problem in result


# ── اکسل ───────────────────────────────────────────────────────────────
def _xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    """کوچک‌ترین بستهٔ xlsx که پارسر را می‌سنجد: رشته‌های مشترک، عدد و رشتهٔ درون‌خطی."""
    strings: list[str] = []

    def cell(ref: str, value: object) -> str:
        if isinstance(value, int | float):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if value is None or value == "":
            return ""
        strings.append(str(value))
        return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'

    sheet_xml: list[str] = []
    for rows in sheets.values():
        body = ""
        for r, row in enumerate(rows, start=1):
            cells = "".join(cell(f"{chr(65 + c)}{r}", v) for c, v in enumerate(row))
            body += f'<row r="{r}">{cells}</row>'
        sheet_xml.append(
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{body}</sheetData></worksheet>"
        )
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheet_tags = "".join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(sheets, start=1)
    )
    rel_tags = "".join(
        f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>{sheet_tags}</sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rel_tags}</Relationships>",
        )
        for i, xml in enumerate(sheet_xml, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
        z.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{ns}">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>",
        )
    return path


def test_reader_finds_the_header_below_title_rows_and_reads_numbers(tmp_path: Path) -> None:
    path = _xlsx(
        tmp_path / "s.xlsx",
        {
            "مهندسی ترابری": [
                ["لیست دانشجویان درس : مهندسی ترابری"],
                ["جستجو:"],
                ["ردیف", "نام", "نام خانوادگی", "شماره دانشجويی", "ایمیل"],  # «ي» عربی
                [1, "علی", "رضایی", 402123456, "Ali@Eng.Example.ac.ir"],
                [2, "سارا", "کریمی", 4.02123457e8, ""],  # اکسل: نمایش علمی، بی‌ایمیل
                [3, "ناقص", "", 402123458, ""],  # نام خانوادگی ندارد
                [4, "بد", "ایمیل", 402123459, "not-an-email"],
            ],
            "Sheet2": [],
        },
    )
    main, empty = read_rosters(path)
    assert [r.student_no_raw for r in main.rows] == ["402123456", "402123457", "402123459"]
    assert main.rows[0].email == "ali@eng.example.ac.ir"  # کوچک‌شده
    assert main.rows[1].email is None
    assert main.skipped == 1 and main.bad_emails == 1
    assert empty.rows == []


def test_a_sheet_without_a_header_is_empty_not_an_error(tmp_path: Path) -> None:
    path = _xlsx(tmp_path / "s.xlsx", {"x": [["چیز دیگری"], ["۱", "۲"]]})
    (sheet,) = read_rosters(path)
    assert sheet.rows == []


def test_title_normalisation_matches_zwnj_and_arabic_letters() -> None:
    assert normalize_title("تحلیل و مدل سازی ایمنی راه") == normalize_title(
        "تحلیل و مدل‌سازی ایمنی راه"
    )
    assert normalize_title("مهندسي ترابري") == normalize_title("مهندسی ترابری")
