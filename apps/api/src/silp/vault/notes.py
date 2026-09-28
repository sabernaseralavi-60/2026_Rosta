"""خواندن یادداشت‌های Vault — ADR-0030.

یک یادداشت یک فایل `.md` با سرآیند YAML است::

    ---
    title: چرا مدل چهارمرحله‌ای هنوز زنده است؟
    kind: article            # article | book-summary | paper-summary | example | case-study
    status: published        # draft (پیش‌فرض) | published
    access: public           # public | registered | student | member | premium
    topics: [برنامه‌ریزی حمل‌ونقل]
    skills: [مدل چهارمرحله‌ای]
    course: Transportation Planning
    date: 2026-09-28
    cover: research          # کلید عکس سایت یا نشانی https
    slug: four-step-model    # اختیاری ولی برای نشانی پایدار توصیه می‌شود
    ---

    متن…

**پیش‌فرض ایمن:** یادداشتِ بی‌`status` پیش‌نویس است و منتشر نمی‌شود.
این ماژول فقط متن را تحلیل می‌کند؛ هیچ I/O به دیتابیس ندارد.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from silp.models.content import CONTENT_ACCESS, CONTENT_KINDS

#: پوشهٔ محتوا در ریشهٔ Vault (§28 مشخصات: ۱۲_Content).
CONTENT_DIR = "12_Content"
#: سرعت خواندن فارسی، کلمه در دقیقه.
WORDS_PER_MINUTE = 180
SUMMARY_MAX = 240

_FRONTMATTER = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_WIKILINK_EMBED = re.compile(r"!\[\[[^\]]*\]\]")
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_OBSIDIAN_COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
_ZWNJ = "‌"

_KIND_ALIASES = {kind.lower().replace("_", "-"): kind for kind in CONTENT_KINDS}


class NoteError(ValueError):
    """یادداشت نامعتبر. پیام برای مالک نوشته می‌شود، نه توسعه‌دهنده."""


@dataclass(frozen=True, slots=True)
class Note:
    source_path: str
    slug: str
    kind: str
    title_fa: str
    summary: str
    body_md: str
    access: str
    status: str
    topics: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    course_slug: str | None = None
    cover: str | None = None
    published_at: datetime | None = None
    reading_minutes: int = 1
    sha256: str = ""
    warnings: tuple[str, ...] = field(default=())


def slugify(text: str) -> str:
    """نشانی خوانا؛ حروف فارسی حفظ می‌شود (URL یونیکد است)."""
    normalized = unicodedata.normalize("NFKC", text).replace(_ZWNJ, "-").strip().lower()
    normalized = re.sub(r"[^\w\-]+", "-", normalized, flags=re.UNICODE)
    return re.sub(r"-{2,}", "-", normalized).strip("-_")


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER.match(raw)
    if match is None:
        return {}, raw.lstrip("﻿")
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise NoteError(f"سرآیند YAML خراب است: {exc}") from exc
    if not isinstance(data, dict):
        raise NoteError("سرآیند YAML باید کلید و مقدار باشد.")
    return data, raw[match.end() :]


def clean_body(body: str) -> str:
    """پیوندهای Obsidian به متن ساده؛ تعبیه (`![[…]]`) و نظرها حذف می‌شوند."""
    body = body.replace("\r\n", "\n")
    body = _OBSIDIAN_COMMENT.sub("", body)
    body = _WIKILINK_EMBED.sub("", body)
    body = _WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), body)
    return body.strip() + "\n"


def summarize(body: str) -> str:
    """اولین بند متنی، بدون علامت Markdown، تا ۲۴۰ نویسه."""
    for block in re.split(r"\n\s*\n", body):
        line = block.strip()
        if not line or line.startswith(("#", ">", "```", "---", "|", "![")):
            continue
        plain = re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", line)
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) <= SUMMARY_MAX:
            return plain
        return plain[: SUMMARY_MAX - 1].rsplit(" ", 1)[0] + "…"
    return ""


def reading_minutes(body: str) -> int:
    words = len(re.findall(r"\w+", body, flags=re.UNICODE))
    return max(1, math.ceil(words / WORDS_PER_MINUTE))


def _as_list(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = list(re.split(r"[,،]", value))
    if not isinstance(value, list):
        raise NoteError(f"«{name}» باید فهرست باشد.")
    seen: dict[str, None] = {}
    for item in value:
        text = str(item).strip()
        if text:
            seen[text] = None
    return tuple(seen)


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 6, 0, tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
    except ValueError as exc:
        raise NoteError(f"«date» را نمی‌توان خواند: {value}") from exc


def parse_note(raw: str, *, source_path: str) -> Note:
    """متن خام یک فایل ← `Note`. خطا: `NoteError` با پیام فارسی."""
    meta, body = split_frontmatter(raw)
    body = clean_body(body)

    title = str(meta.get("title") or "").strip()
    if not title:
        heading = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
        title = heading.group(1).strip() if heading else ""
    if not 3 <= len(title) <= 200:
        raise NoteError("عنوان لازم است (۳ تا ۲۰۰ نویسه): کلید «title» یا یک سرتیتر «# …».")

    kind_key = str(meta.get("kind") or "article").strip().lower().replace("_", "-")
    if kind_key not in _KIND_ALIASES:
        allowed = ", ".join(sorted(_KIND_ALIASES))
        raise NoteError(f"«kind» نامعتبر است: {kind_key}. مجاز: {allowed}")
    access = str(meta.get("access") or "public").strip().upper()
    if access not in CONTENT_ACCESS:
        allowed = ", ".join(a.lower() for a in CONTENT_ACCESS)
        raise NoteError(f"«access» نامعتبر است: {access.lower()}. مجاز: {allowed}")
    status = str(meta.get("status") or "draft").strip().upper()
    if status not in ("DRAFT", "PUBLISHED"):
        raise NoteError("«status» باید draft یا published باشد.")

    if not body.strip():
        raise NoteError("متن یادداشت خالی است.")
    summary = str(meta.get("summary") or "").strip() or summarize(body)
    if not summary:
        raise NoteError("خلاصه ساخته نشد؛ کلید «summary» را بنویسید.")

    stem = Path(source_path).stem
    slug = slugify(str(meta.get("slug") or "")) or slugify(stem)
    if not slug:
        raise NoteError("نشانی (slug) ساخته نشد؛ کلید «slug» را بنویسید.")

    warnings: list[str] = []
    if "slug" not in meta:
        warnings.append("slug ندارد؛ نام فایل نشانی می‌شود و تغییرش نشانی را عوض می‌کند")
    cover = str(meta["cover"]).strip() if meta.get("cover") else None
    if cover and not (cover.startswith("https://") or re.fullmatch(r"[a-z0-9_-]+", cover)):
        raise NoteError("«cover» باید کلید عکس سایت یا نشانی https باشد.")

    return Note(
        source_path=source_path,
        slug=slug,
        kind=_KIND_ALIASES[kind_key],
        title_fa=title,
        summary=summary,
        body_md=body,
        access=access,
        status=status,
        topics=_as_list(meta.get("topics"), "topics"),
        skills=_as_list(meta.get("skills"), "skills"),
        course_slug=str(meta["course"]).strip() if meta.get("course") else None,
        cover=cover,
        published_at=_as_datetime(meta.get("date")),
        reading_minutes=reading_minutes(body),
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        warnings=tuple(warnings),
    )


__all__ = [
    "CONTENT_DIR",
    "Note",
    "NoteError",
    "clean_body",
    "parse_note",
    "reading_minutes",
    "slugify",
    "split_frontmatter",
    "summarize",
]
