"""نقطهٔ ورود Vercel (تابع بدون‌سرور). اپ اصلی همان ``silp.main:app`` است."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from silp.main import app  # noqa: E402, F401
