"""ساخت جفت‌کلید VAPID برای اعلان Push — ADR-0029.

    python -m silp.scripts.gen_vapid_keys

خروجی دو خط `.env` است. کلید خصوصی را فقط در `.env` سرور نگه دار. کلید
عمومی همان است که مرورگر هنگام اشتراک می‌گیرد؛ **اگر عوض شود، همهٔ
اشتراک‌های موجود بی‌اثر می‌شوند** (سرویس Push کلید امضاکننده را با
اشتراک گره می‌زند) و کاربران باید دوباره روشنش کنند.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    """(کلید عمومی، کلید خصوصی) هر دو base64 امن‌برای‌URL."""
    vapid = Vapid()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return _b64(public), _b64(private)


def main() -> None:
    public, private = generate()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")


if __name__ == "__main__":
    main()
