"""ابزار Vault شخصی مالک — ADR-0030.

اجرا (از `apps/api`)::

    python -m silp.scripts.vault init                       # ساخت ساختار Vault
    python -m silp.scripts.vault publish                    # پیش‌نمایش انتشار 12_Content
    python -m silp.scripts.vault publish --apply            # انتشار واقعی
    python -m silp.scripts.vault push                       # پیش‌نمایش انتشار روی سرور (API)
    python -m silp.scripts.vault push --apply               # انتشار واقعی روی سرور
    python -m silp.scripts.vault export                     # آینهٔ دادهٔ سایت ← Vault
    python -m silp.scripts.vault broadcast 14_AI/broadcasts/پیام.md          # پیش‌نمایش
    python -m silp.scripts.vault broadcast 14_AI/broadcasts/پیام.md --send   # ارسال

مسیر Vault: `--vault` یا متغیر محیطی `SILP_VAULT`.
`push` به دیتابیس نمی‌رسد؛ به API سرور با `SILP_API_URL` و `SILP_API_TOKEN` وصل می‌شود
(توکن را `python -m silp.scripts.api_token create` روی سرور می‌سازد — ADR-0031).

پیش‌فرض همهٔ دستورهای نویسنده **پیش‌نمایش** است؛ `--apply` و `--send` صریح‌اند.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from silp.core.config import get_settings
from silp.core.logging import configure_logging
from silp.db.session import dispose_engine, get_session_factory
from silp.vault import broadcast as broadcast_mod
from silp.vault.exporter import EXPORTERS, export_vault
from silp.vault.notes import CONTENT_DIR, NoteError
from silp.vault.publisher import PublishReport, collect, publish_vault
from silp.vault.skeleton import init_vault


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vault", description="Vault شخصی مالک")
    parser.add_argument("--vault", type=Path, default=None, help="مسیر Vault (یا SILP_VAULT)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="ساخت پوشه‌ها و راهنماها (بدون بازنویسی)")

    publish = sub.add_parser("publish", help="انتشار یادداشت‌های 12_Content")
    publish.add_argument("--apply", action="store_true", help="واقعاً بنویس (پیش‌فرض: پیش‌نمایش)")
    publish.add_argument(
        "--keep-missing", action="store_true", help="فایل‌های ناپدیدشده آرشیو نشوند"
    )

    push = sub.add_parser("push", help="انتشار 12_Content روی سرور از راه API")
    push.add_argument("--apply", action="store_true", help="واقعاً بنویس (پیش‌فرض: پیش‌نمایش)")
    push.add_argument("--keep-missing", action="store_true", help="فایل‌های ناپدیدشده آرشیو نشوند")
    push.add_argument("--url", default=None, help="نشانی سرور (یا SILP_API_URL)")

    export = sub.add_parser("export", help="آینهٔ دادهٔ سایت در Vault")
    export.add_argument("--only", choices=sorted(EXPORTERS), action="append", default=[])

    bcast = sub.add_parser("broadcast", help="پیام گروهی از یک فایل")
    bcast.add_argument("file", type=Path, help="فایل پیام (نسبت به Vault یا مطلق)")
    bcast.add_argument("--send", action="store_true", help="واقعاً بفرست (پیش‌فرض: پیش‌نمایش)")
    return parser.parse_args(argv)


def _vault(args: argparse.Namespace) -> Path:
    raw = args.vault or os.environ.get("SILP_VAULT")
    if not raw:
        print("مسیر Vault را با --vault یا متغیر SILP_VAULT بدهید.", file=sys.stderr)
        raise SystemExit(2)
    return Path(raw).expanduser().resolve()


def _print_publish(report: PublishReport, *, applied: bool) -> None:
    print("")
    print(
        "  انتشار واقعی." if applied else "  «پیش‌نمایش» — هیچ‌چیز نوشته نشد؛ با --apply اجرا کنید."
    )
    for label, items in (
        ("تازه", report.created),
        ("به‌روز", report.updated),
        ("بدون تغییر", report.unchanged),
        ("آرشیو", report.archived),
    ):
        print(f"  {label}: {len(items)}")
        for path in items if label != "بدون تغییر" else []:
            print(f"      {path}")
    for path, warnings in report.warnings.items():
        for warning in warnings:
            print(f"  ! هشدار {path}: {warning}")
    for path, error in report.errors.items():
        print(f"  ✗ {path}: {error}")
    print("")


async def _publish(vault: Path, args: argparse.Namespace) -> int:
    async with get_session_factory()() as session:
        report = await publish_vault(session, vault, archive_missing=not args.keep_missing)
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    _print_publish(report, applied=args.apply)
    return 0 if report.ok else 1


def _server(args: argparse.Namespace) -> tuple[str, str] | None:
    base = (args.url or os.environ.get("SILP_API_URL") or "").rstrip("/")
    token = os.environ.get("SILP_API_TOKEN", "")
    if not base or not token:
        print(
            "نشانی سرور را با --url یا SILP_API_URL و توکن را با SILP_API_TOKEN بدهید.",
            file=sys.stderr,
        )
        return None
    host = urlsplit(base).hostname or ""
    if not base.startswith("https://") and host not in ("localhost", "127.0.0.1", "::1"):
        # توکن در هدر می‌رود؛ روی http ساده شنود می‌شود.
        print("نشانی باید https باشد (فقط localhost استثناست).", file=sys.stderr)
        return None
    return base, token


async def _push(vault: Path, args: argparse.Namespace) -> int:
    server = _server(args)
    if server is None:
        return 2
    base, token = server
    files, unreadable = collect(vault)
    payload = {
        "notes": [{"path": path, "raw": raw} for path, raw in files],
        "apply": args.apply,
        # پوشهٔ محتوا نبود (دیسک وصل نیست)، یا کاربر خواست: هیچ‌چیز آرشیو نشود.
        "complete": not args.keep_missing and CONTENT_DIR not in unreadable,
        "client_errors": unreadable,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{base}/api/v1/vault/publish",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        print(f"به سرور نرسید: {exc}", file=sys.stderr)
        return 1
    if response.status_code != httpx.codes.OK:
        try:
            detail = response.json().get("error", {}).get("message") or response.text
        except ValueError:
            detail = response.text
        print(f"سرور رد کرد ({response.status_code}): {detail}", file=sys.stderr)
        return 1
    body = response.json()
    report = PublishReport(
        created=body["created"],
        updated=body["updated"],
        unchanged=body["unchanged"],
        archived=body["archived"],
        errors=body["errors"],
        warnings={path: tuple(w) for path, w in body["warnings"].items()},
    )
    _print_publish(report, applied=body["applied"])
    return 0 if report.ok else 1


async def _export(vault: Path, args: argparse.Namespace) -> int:
    async with get_session_factory()() as session:
        report = await export_vault(session, vault, only=tuple(args.only))
    print(f"\n  نوشته‌شده: {len(report.written)} · بدون تغییر: {len(report.unchanged)}\n")
    return 0


async def _broadcast(vault: Path, args: argparse.Namespace) -> int:
    path = args.file if args.file.is_absolute() else vault / args.file
    try:
        message = broadcast_mod.load_broadcast(path)
    except NoteError as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 1
    async with get_session_factory()() as session:
        result = await broadcast_mod.run_broadcast(session, message, send=args.send)
        if args.send:
            await session.commit()
        else:
            await session.rollback()
    print("")
    print(f"  «{message.title}» ← {message.audience}: {result.recipients} مخاطب")
    if not args.send:
        print("  «پیش‌نمایش» — چیزی ارسال نشد؛ برای ارسال --send بزنید.")
    else:
        print(
            f"  {result.created} پیام تازه در صف، {result.already_received} نفر قبلاً گرفته بودند."
        )
        broadcast_mod.append_log(vault, message, result)
    print("")
    return 0


async def main(argv: list[str] | None = None) -> int:
    args = _parse(argv if argv is not None else sys.argv[1:])
    vault = _vault(args)
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")

    if args.command == "init":
        vault.mkdir(parents=True, exist_ok=True)
        created = init_vault(vault)
        print(f"\n  Vault: {vault}\n  {len(created)} مورد تازه ساخته شد.\n")
        return 0

    if args.command == "push":
        # رایانهٔ مالک تنظیمات سرور (DATABASE_URL، کلیدها…) ندارد و لازم هم ندارد.
        return await _push(vault, args)

    configure_logging(get_settings().log_level, renderer="console")
    try:
        if args.command == "publish":
            return await _publish(vault, args)
        if args.command == "export":
            return await _export(vault, args)
        return await _broadcast(vault, args)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
