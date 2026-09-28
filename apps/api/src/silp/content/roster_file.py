"""خواندن فهرست دانشجویان از اکسل (.xlsx) بدون هیچ وابستگی — ADR-0035.

فقط کتابخانهٔ استاندارد: `zipfile` و `xml`. فایل‌های اکسل بسته‌ای از XML‌اند؛ برای این کار
کوچک، وابستگی تازه (openpyxl) به زنجیرهٔ تأمین اضافه نمی‌کنیم.

ورودی فایلِ محلیِ خود استاد است، نه آپلود کاربر؛ به همین دلیل هشدار S314 (XML
نامطمئن) پذیرفته شده است. اگر روزی این خواندن به آپلود وب رسید، باید با `defusedxml` عوض شود.

قالب مورد انتظار (هر برگه = یک درس): جایی در برگه ردیفی با سرستون‌های «نام»،
«نام خانوادگی»، «شماره دانشجویی» و (اختیاری) «ایمیل»؛ ردیف‌های بعدی دانشجویان‌اند.
ردیف‌های بالای سرستون (عنوان، «جستجو:») نادیده گرفته می‌شوند.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

from silp.domain.identity.normalize import EMAIL_RE

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_COLUMN = re.compile(r"^([A-Z]+)")

FIRST, LAST, NUMBER, EMAIL = "نام", "نام خانوادگی", "شماره دانشجویی", "ایمیل"


@dataclass(frozen=True, slots=True)
class RosterRow:
    first_name: str
    last_name: str
    student_no_raw: str
    email: str | None


@dataclass(frozen=True, slots=True)
class SheetRoster:
    name: str
    rows: list[RosterRow]
    #: ردیف‌هایی که نام یا شمارهٔ دانشجویی نداشتند (بدون ذکر محتوا)
    skipped: int
    #: ایمیل‌های ناقص که نادیده گرفته شدند
    bad_emails: int


def _normalize_label(value: str) -> str:
    """ي/ك عربی، نیم‌فاصله و فاصلهٔ اضافه را یکدست می‌کند تا «نام خانوادگی» هر جور تایپ شد بخورد."""
    text = value.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", text).strip()


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))  # noqa: S314
    return ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root]


def _sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))  # noqa: S314
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))  # noqa: S314
    targets = {rel.get("Id"): rel.get("Target", "") for rel in rels}
    result: list[tuple[str, str]] = []
    sheets = workbook.find("m:sheets", _NS)
    for sheet in sheets if sheets is not None else []:
        target = targets.get(sheet.get(f"{{{_NS['r']}}}id"), "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        result.append((sheet.get("name") or "", path))
    return result


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t")).strip()
    value = cell.find("m:v", _NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return strings[int(value.text)].strip()
    text = value.text.strip()
    # اکسل عدد را گاهی «4.02123456E8» ذخیره می‌کند.
    if kind in (None, "n") and re.search(r"[.eE]", text):
        try:
            number = Decimal(text)
        except InvalidOperation:
            return text
        if number == number.to_integral_value():
            return str(int(number))
    return text


def _rows(sheet: ET.Element, strings: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        cells: dict[str, str] = {}
        for cell in row.findall("m:c", _NS):
            match = _COLUMN.match(cell.get("r", ""))
            if match:
                text = _cell_text(cell, strings)
                if text:
                    cells[match.group(1)] = text
        out.append(cells)
    return out


def read_rosters(path: Path) -> list[SheetRoster]:
    """همهٔ برگه‌ها. برگه‌ای که سرستون «شماره دانشجویی» نداشته باشد، خالی گزارش می‌شود."""
    rosters: list[SheetRoster] = []
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        for name, sheet_path in _sheet_paths(archive):
            sheet = ET.fromstring(archive.read(sheet_path))  # noqa: S314
            rosters.append(_roster_of(name, _rows(sheet, strings)))
    return rosters


def _roster_of(name: str, rows: list[dict[str, str]]) -> SheetRoster:
    header_at = None
    columns: dict[str, str] = {}
    for index, row in enumerate(rows):
        labels = {_normalize_label(text): col for col, text in row.items()}
        if NUMBER in labels and FIRST in labels and LAST in labels:
            header_at, columns = index, labels
            break
    if header_at is None:
        return SheetRoster(name=name, rows=[], skipped=0, bad_emails=0)

    out: list[RosterRow] = []
    skipped = bad_emails = 0
    for row in rows[header_at + 1 :]:
        if not row:
            continue
        first = row.get(columns[FIRST], "")
        last = row.get(columns[LAST], "")
        number = row.get(columns[NUMBER], "")
        if not (first and last and number):
            skipped += 1
            continue
        email: str | None = None
        if EMAIL in columns:
            raw = row.get(columns[EMAIL], "").strip().lower()
            if raw and EMAIL_RE.match(raw):
                email = raw
            elif raw:
                bad_emails += 1
        out.append(RosterRow(first_name=first, last_name=last, student_no_raw=number, email=email))
    return SheetRoster(name=name, rows=out, skipped=skipped, bad_emails=bad_emails)


def normalize_title(value: str) -> str:
    """برای تطبیق نام برگه با عنوان درس."""
    return _normalize_label(value)
