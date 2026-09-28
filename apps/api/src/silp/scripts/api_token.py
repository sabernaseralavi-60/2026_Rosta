"""مدیریت توکن دسترسی برنامه‌ای — ADR-0031.

اجرا (روی **سرور**، با همان متغیرهای محیطی API)::

    python -m silp.scripts.api_token create --mobile 09121234567 --name "رایانهٔ خانه"
    python -m silp.scripts.api_token list   --mobile 09121234567
    python -m silp.scripts.api_token revoke --mobile 09121234567 <شناسهٔ توکن>

توکن ساخته‌شده **فقط همین‌جا** نمایش داده می‌شود. صاحب توکن باید کاربری با نقش
ADMIN باشد؛ مجوز هر بار هنگام استفاده دوباره سنجیده می‌شود.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
import uuid

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.logging import configure_logging
from silp.core.permissions import CurrentUser, Permission
from silp.db.session import dispose_engine, get_session_factory
from silp.domain.identity.normalize import normalize_mobile
from silp.models.api_token import TOKEN_SCOPES
from silp.models.identity import User
from silp.services import authz
from silp.services.api_token_service import ApiTokenService


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="api_token", description="توکن دسترسی برنامه‌ای")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="ساخت توکن تازه")
    create.add_argument("--mobile", required=True, help="موبایل مالک (ادمین)")
    create.add_argument("--name", required=True, help="نام توکن، مثل «رایانهٔ خانه»")
    create.add_argument("--scope", action="append", choices=TOKEN_SCOPES, default=[])
    create.add_argument("--days", type=int, default=None, help="انقضا به روز (پیش‌فرض: بی‌انقضا)")

    listing = sub.add_parser("list", help="فهرست توکن‌های یک کاربر")
    listing.add_argument("--mobile", required=True)

    revoke = sub.add_parser("revoke", help="ابطال توکن")
    revoke.add_argument("--mobile", required=True)
    revoke.add_argument("token_id", type=uuid.UUID)
    return parser.parse_args(argv)


async def _user(mobile_raw: str) -> User | None:
    mobile = normalize_mobile(mobile_raw)
    if mobile is None:
        print("شمارهٔ موبایل معتبر نیست.", file=sys.stderr)
        return None
    async with get_session_factory()() as session:
        user = await session.scalar(select(User).where(User.mobile == mobile))
    if user is None:
        print("کاربری با این شماره نیست.", file=sys.stderr)
    return user


async def _create(args: argparse.Namespace) -> int:
    user = await _user(args.mobile)
    if user is None:
        return 1
    async with get_session_factory()() as session:
        grants = await authz.load_grants(session, user.id)
        if not CurrentUser(id=user.id, session_id=user.id, grants=grants).has_permission(
            Permission.CONTENT_PUBLISH
        ):
            print("این کاربر مجوز انتشار محتوا (نقش ADMIN) ندارد.", file=sys.stderr)
            return 1
        row, raw = await ApiTokenService(session).create(
            user.id,
            name=args.name,
            scopes=args.scope or ["vault:publish"],
            expires_in_days=args.days,
        )
        await session.commit()
    print("")
    print(f"  توکن «{row.name}» ساخته شد ({row.id}).")
    print("  این متن را همین حالا نگه دارید؛ دوباره دیده نمی‌شود:")
    print("")
    print(f"      {raw}")
    print("")
    print("  روی رایانهٔ خود:  set SILP_API_TOKEN=<توکن>   و   set SILP_API_URL=https://…")
    print("")
    return 0


async def _list(args: argparse.Namespace) -> int:
    user = await _user(args.mobile)
    if user is None:
        return 1
    async with get_session_factory()() as session:
        rows = await ApiTokenService(session).list_for(user.id)
    print("")
    for row in rows:
        state = "ابطال‌شده" if row.revoked_at else "فعال"
        used = row.last_used_at.isoformat(timespec="minutes") if row.last_used_at else "هرگز"
        print(f"  {row.id}  {row.token_hint}…  {state}  آخرین استفاده: {used}  «{row.name}»")
    print(f"\n  {len(rows)} توکن.\n")
    return 0


async def _revoke(args: argparse.Namespace) -> int:
    user = await _user(args.mobile)
    if user is None:
        return 1
    async with get_session_factory()() as session:
        done = await ApiTokenService(session).revoke(args.token_id, user_id=user.id)
        await session.commit()
    print("\n  ابطال شد.\n" if done else "\n  توکنی با این شناسه برای این کاربر نیست.\n")
    return 0 if done else 1


async def main(argv: list[str] | None = None) -> int:
    args = _parse(argv if argv is not None else sys.argv[1:])
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    configure_logging(get_settings().log_level, renderer="console")
    try:
        handler = {"create": _create, "list": _list, "revoke": _revoke}[args.command]
        return await handler(args)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
