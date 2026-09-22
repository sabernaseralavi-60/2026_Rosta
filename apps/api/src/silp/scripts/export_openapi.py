"""صدور اسکیمای OpenAPI به stdout — برای `make types`.

خروجی به `packages/shared/openapi.json` هدایت می‌شود و از روی آن تایپ‌های
TypeScript ساخته می‌شوند (PRD §12.3). در CI همین خروجی با نسخهٔ main
مقایسه می‌شود تا تغییر شکننده هشدار بدهد.
"""

from __future__ import annotations

import json
import sys

from silp.main import create_app


def main() -> int:
    app = create_app()
    schema = app.openapi()
    # sort_keys تا تفاوت‌های بی‌معنا در diff ظاهر نشوند.
    json.dump(schema, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
