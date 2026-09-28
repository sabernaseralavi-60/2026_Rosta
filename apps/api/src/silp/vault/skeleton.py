"""ساختار Vault شخصی مالک — §28 مشخصات، ADR-0030.

`vault init` این پوشه‌ها و راهنماها را می‌سازد و **هیچ فایلی را بازنویسی نمی‌کند**.
Vault با Obsidian سازگار است ولی به آن وابسته نیست؛ همه‌چیز Markdown ساده است.
"""

from __future__ import annotations

from pathlib import Path

FOLDERS: tuple[str, ...] = (
    "00_Inbox",
    "01_People",
    "02_Students",
    "03_Clients",
    "04_Projects",
    "05_Courses",
    "06_Research",
    "07_Datasets",
    "08_Papers",
    "09_Business",
    "10_Meetings",
    "11_Decisions",
    "12_Content",
    "13_Ideas",
    "14_AI",
    "14_AI/broadcasts",
    "99_Archive",
)

README = """# Vault سامانه

این پوشه **فقط روی رایانهٔ شخصی شما** است و در Git یا GitHub قرار نمی‌گیرد.

| پوشه | نقش | جهت |
|------|-----|-----|
| `12_Content/` | مقاله، خلاصهٔ کتاب و مقاله، مثال، Case Study — **شما می‌نویسید** | Vault ← سایت |
| `14_AI/broadcasts/` | پیام گروهی به دانشجویان و مخاطبان — **شما می‌نویسید** | Vault ← سایت |
| `02_Students/`، `04_Projects/`، `05_Courses/` | آینهٔ دادهٔ سایت (خودکار) | سایت ← Vault |
| بقیه | یادداشت‌های شخصی شما | فقط محلی |

فایل‌های آینه با `generated: true` علامت خورده‌اند و با هر `vault export` بازنویسی
می‌شوند؛ یادداشت شخصی‌تان را کنارشان بنویسید، نه داخلشان.

## دستورها

```
python -m silp.scripts.vault init                # ساخت همین ساختار
python -m silp.scripts.vault publish             # انتشار 12_Content (بدون --apply فقط پیش‌نمایش)
python -m silp.scripts.vault export              # ساخت آینهٔ دادهٔ سایت
python -m silp.scripts.vault broadcast <فایل>    # پیش‌نمایش پیام گروهی؛ با --send ارسال
```

مسیر Vault از `--vault` یا متغیر محیطی `SILP_VAULT` خوانده می‌شود.
"""

CONTENT_TEMPLATE = """---
title: عنوان یادداشت
kind: article        # article | book-summary | paper-summary | example | case-study | dataset-note
status: draft        # draft = منتشر نمی‌شود · published = منتشر می‌شود
access: public       # public | registered | student | member | premium
topics: [برنامه‌ریزی حمل‌ونقل]
skills: []
course:              # نام پوشهٔ درس در Courses/ (اختیاری)
date: 2026-01-01     # تاریخ انتشار (اختیاری)
cover:               # کلید عکس سایت (hero, learn, research, solve, collab, agri) یا نشانی https
slug: my-first-note  # نشانی پایدار صفحه؛ بعد از انتشار عوضش نکنید
---

بند اول، خلاصهٔ یادداشت را می‌سازد (اگر `summary:` ننویسید).

## سرتیتر

متن با Markdown. پیوند `[[یادداشت دیگر]]` به متن ساده تبدیل می‌شود.
"""

BROADCAST_TEMPLATE = """---
title: عنوان پیام
audience: students   # students | all | offering:<شناسه> | user:<موبایل>
---

متن پیام. برای هر گیرنده در ایمیل، نام او خودکار در ابتدای پیام می‌آید.
"""

FILES: dict[str, str] = {
    "README.md": README,
    "12_Content/_template.md": CONTENT_TEMPLATE,
    "14_AI/broadcasts/_template.md": BROADCAST_TEMPLATE,
}


def init_vault(root: Path) -> list[str]:
    """ساخت پوشه‌ها و راهنماها. خروجی: مسیرهای **تازه** ساخته‌شده."""
    created: list[str] = []
    for folder in FOLDERS:
        target = root / folder
        if not target.exists():
            target.mkdir(parents=True)
            created.append(f"{folder}/")
    for relative, content in FILES.items():
        target = root / relative
        if not target.exists():
            target.write_text(content, encoding="utf-8", newline="\n")
            created.append(relative)
    return created


__all__ = ["FILES", "FOLDERS", "init_vault"]
