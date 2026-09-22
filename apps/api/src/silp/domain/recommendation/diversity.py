"""بازچینش نتایج برای تنوع — PRD §8.11.

اگر ده پیشنهاد برتر همه از یک نوع باشند، دانشجو تصویر محدودی از سامانه
می‌گیرد و گمان می‌کند SILP فقط «جای پروژه‌های پژوهشی» است. دو قاعده:

۱. حداکثر چهار پروژه از یک نوع در ده نتیجهٔ اول.
۲. حداقل یک پروژهٔ «کشش‌دار» (دشوارتر از سطح فعلی دانشجو)، با برچسب
   «چالش‌برانگیز — اگر آماده‌ای».

منطق خالص است: فهرست مرتب می‌گیرد و فهرست مرتب برمی‌گرداند.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from silp.domain.recommendation.schemas import MatchResult, ProjectKind

MAX_PER_KIND = 4
DEFAULT_RESULT_SIZE = 10


def diversify(
    ranked: Sequence[MatchResult],
    k: int = DEFAULT_RESULT_SIZE,
    *,
    max_per_kind: int = MAX_PER_KIND,
) -> list[MatchResult]:
    """بازچینش حداکثر حاشیه‌ای سبک (MMR-lite) — §8.11.

    ورودی باید از پیش بر اساس امتیاز مرتب باشد. خروجی همان ترتیب نسبی را
    نگه می‌دارد و فقط موارد اضافی یک نوع را عقب می‌اندازد — کاری که رتبهٔ
    اول را هرگز عوض نمی‌کند.
    """
    if k <= 0:
        return []

    chosen: list[MatchResult] = []
    deferred: list[MatchResult] = []
    per_kind: Counter[ProjectKind] = Counter()

    for match in ranked:
        if len(chosen) == k:
            break
        if per_kind[match.kind] >= max_per_kind:
            deferred.append(match)
            continue
        chosen.append(match)
        per_kind[match.kind] += 1

    # سهمیه همهٔ جاها را پر نکرد؟ از کنارگذاشته‌ها ادامه بده — بهتر از
    # برگرداندن فهرست کوتاه است.
    if len(chosen) < k:
        seen = {id(m) for m in chosen}
        remaining = [m for m in [*deferred, *ranked] if id(m) not in seen]
        for match in remaining:
            if len(chosen) == k:
                break
            if id(match) in seen:
                continue
            chosen.append(match)
            seen.add(id(match))

    return chosen


def ensure_stretch(
    chosen: Sequence[MatchResult],
    pool: Sequence[MatchResult],
    k: int = DEFAULT_RESULT_SIZE,
) -> list[MatchResult]:
    """تضمین حضور حداقل یک پروژهٔ کشش‌دار — §8.11.

    اگر در نتایج انتخابی هیچ پروژهٔ دشوارتری نبود، بهترین کشش‌دارِ موجود
    جای **آخرین** نتیجه را می‌گیرد؛ رتبه‌های بالا دست نمی‌خورند.
    """
    result = list(chosen)
    if any(m.is_stretch for m in result):
        return result

    selected = {m.project.id for m in result}
    stretch = next((m for m in pool if m.is_stretch and m.project.id not in selected), None)
    if stretch is None:
        return result

    if len(result) < k:
        result.append(stretch)
    else:
        result[-1] = stretch
    return result


__all__ = ["DEFAULT_RESULT_SIZE", "MAX_PER_KIND", "diversify", "ensure_stretch"]
