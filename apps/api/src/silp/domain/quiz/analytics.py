"""تحلیل پیشرفتهٔ آزمون — §3.5، ADR-0028. منطق خالص، بدون I/O.

سه چیز که تحلیل هر سؤال (M4-13) به‌تنهایی نمی‌گوید:

* **کل آزمون:** توزیع نمره، میانگین، میانه، انحراف معیار.
* **پایایی:** آلفای کرونباخ (برای سؤال‌های صفر/یکی همان KR-20) و خطای معیار
  اندازه‌گیری. آزمونی که پایایی‌اش پایین است، نمرهٔ دانشجو را «دقیق» نشان
  نمی‌دهد — حتی اگر تک‌تک سؤال‌ها سالم به‌نظر برسند.
* **توزیع گزینه:** کدام گزینهٔ غلط را چه کسی می‌زند. گزینه‌ای که هیچ‌کس
  نمی‌زند، گزینه نیست؛ گزینه‌ای که قوی‌ترها بیشتر می‌زنند، یا غلط است یا
  کلیدِ سؤال.

همهٔ شاخص‌ها زیر `MIN_COHORT` تلاش `None` می‌مانند: نویزی که شکل شاخص
دارد، بدتر از نبودن شاخص است (همان تصمیم M4-13).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: زیر این تعداد تلاش، شاخص‌های همبستگی و پایایی محاسبه نمی‌شود.
MIN_COHORT = 10
#: سهم گروه بالا و پایین برای توزیع گزینه (قاعدهٔ ۲۷٪ کلی).
GROUP_RATIO = 0.27
#: گزینهٔ غلطی که کمتر از این سهم از کلاس انتخابش کرده، «بی‌کاربرد» است.
DEAD_OPTION_SHARE = 0.05
#: اختلاف سهم گروه بالا و پایین برای هشدار «قوی‌ترها این گزینه را می‌زنند».
ATTRACTS_STRONG_GAP = 0.10
HISTOGRAM_BINS = 10


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    """توزیع نمرهٔ کل آزمون. نمره‌ها به درصد بارم کل برگردانده می‌شوند."""

    n: int
    mean_percent: float
    median_percent: float
    #: انحراف معیار نمونه (n−1)؛ `None` با کمتر از دو تلاش.
    sd_percent: float | None
    min_percent: float
    max_percent: float
    #: `HISTOGRAM_BINS` سطل مساوی از ۰ تا ۱۰۰٪؛ سطل آخر ۱۰۰٪ را هم دربر می‌گیرد.
    histogram: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Reliability:
    alpha: float
    #: خطای معیار اندازه‌گیری به درصد بارم کل: `sd·√(1−α)`.
    sem_percent: float
    label_fa: str
    advice_fa: str | None


@dataclass(frozen=True, slots=True)
class OptionStat:
    option_id: str
    text: str
    is_correct: bool
    chosen: int
    #: سهم از **همهٔ** تلاش‌ها (نه فقط پاسخ‌دهندگان)، ۰ تا ۱.
    share: float
    #: سهم در گروه بالا/پایین؛ `None` زیر `MIN_COHORT`.
    top_share: float | None
    bottom_share: float | None
    note_fa: str | None


def summarize_scores(percents: Sequence[float]) -> ScoreSummary | None:
    """`percents` درصد نمرهٔ هر تلاش از بارمِ همان تلاش است (۰ تا ۱۰۰).

    درصد، نه نمرهٔ خام: با انتخاب تصادفی از بانک سؤال، بارم کل تلاش‌ها
    یکی نیست. بدون تلاش `None`.
    """
    if not percents:
        return None
    percents = sorted(percents)
    n = len(percents)
    mean = math.fsum(percents) / n
    middle = n // 2
    median = percents[middle] if n % 2 else (percents[middle - 1] + percents[middle]) / 2
    sd = math.sqrt(math.fsum((p - mean) ** 2 for p in percents) / (n - 1)) if n > 1 else None

    histogram = [0] * HISTOGRAM_BINS
    for percent in percents:
        histogram[min(HISTOGRAM_BINS - 1, int(percent // (100 / HISTOGRAM_BINS)))] += 1

    return ScoreSummary(
        n=n,
        mean_percent=mean,
        median_percent=median,
        sd_percent=sd,
        min_percent=percents[0],
        max_percent=percents[-1],
        histogram=tuple(histogram),
    )


def cronbach_alpha(matrix: Sequence[Sequence[float]]) -> float | None:
    """آلفای کرونباخ. `matrix[i][j]` نمرهٔ تلاش `i` در سؤال `j` است.

    `None` اگر کمتر از `MIN_COHORT` تلاش، کمتر از دو سؤال، یا واریانس نمرهٔ کل
    صفر باشد (همه یک نمره گرفته‌اند — «پایایی» معنایی ندارد).
    """
    n = len(matrix)
    if n < MIN_COHORT:
        return None
    k = len(matrix[0])
    if k < 2:
        return None
    columns = list(zip(*matrix, strict=True))
    total_variance = _variance([math.fsum(row) for row in matrix])
    if total_variance <= 0:
        return None
    item_variance = math.fsum(_variance(column) for column in columns)
    return (k / (k - 1)) * (1 - item_variance / total_variance)


def reliability(matrix: Sequence[Sequence[float]], max_total: float) -> Reliability | None:
    alpha = cronbach_alpha(matrix)
    if alpha is None or max_total <= 0:
        return None
    total_sd = math.sqrt(_variance([math.fsum(row) for row in matrix]))
    sem = total_sd * math.sqrt(max(0.0, 1 - alpha))
    label, advice = _alpha_band(alpha)
    return Reliability(
        alpha=alpha,
        sem_percent=100.0 * sem / max_total,
        label_fa=label,
        advice_fa=advice,
    )


def item_rest_correlation(item: Sequence[float], totals: Sequence[float]) -> float | None:
    """همبستگی پیرسون سؤال با نمرهٔ **بقیهٔ** آزمون (خودش کم می‌شود).

    اگر خود سؤال در مجموع بماند، همبستگی به‌خاطر سهم خودش بالا می‌رود؛ با
    آزمون کوتاه این اریبی بزرگ است. `None` زیر `MIN_COHORT` یا با واریانس صفر.
    """
    if len(item) < MIN_COHORT or len(item) != len(totals):
        return None
    rest = [t - i for i, t in zip(item, totals, strict=True)]
    var_item, var_rest = _variance(item), _variance(rest)
    if var_item <= 0 or var_rest <= 0:
        return None
    mean_item = math.fsum(item) / len(item)
    mean_rest = math.fsum(rest) / len(rest)
    covariance = math.fsum(
        (i - mean_item) * (r - mean_rest) for i, r in zip(item, rest, strict=True)
    ) / (len(item) - 1)
    return covariance / math.sqrt(var_item * var_rest)


def option_stats(
    *,
    options: Sequence[tuple[str, str, bool]],
    selections: Mapping[str, Sequence[str]],
    totals: Mapping[str, float],
) -> list[OptionStat]:
    """توزیع گزینه‌های یک سؤال چندگزینه‌ای.

    * `options`: `(شناسه، متن، درست‌است؟)` به ترتیب سؤال.
    * `selections`: شناسهٔ تلاش ← گزینه‌هایی که زده. تلاشی که به سؤال جواب
      نداده هم باید کلید داشته باشد (با فهرست خالی) تا مخرجِ سهم‌ها کل کلاس باشد.
    * `totals`: شناسهٔ تلاش ← نمرهٔ کل، برای تقسیم به گروه بالا و پایین.
    """
    n = len(selections)
    if n == 0:
        return []

    ranked = sorted(selections, key=lambda attempt: totals.get(attempt, 0.0), reverse=True)
    group = int(n * GROUP_RATIO) if n >= MIN_COHORT else 0
    top, bottom = ranked[:group], ranked[-group:] if group else []

    def share(members: Sequence[str], option_id: str) -> float:
        return sum(option_id in selections[m] for m in members) / len(members)

    result: list[OptionStat] = []
    for option_id, text, is_correct in options:
        chosen = sum(option_id in picked for picked in selections.values())
        share_all = chosen / n
        top_share = share(top, option_id) if group else None
        bottom_share = share(bottom, option_id) if group else None
        result.append(
            OptionStat(
                option_id=option_id,
                text=text,
                is_correct=is_correct,
                chosen=chosen,
                share=share_all,
                top_share=top_share,
                bottom_share=bottom_share,
                note_fa=_option_note(is_correct, n, share_all, top_share, bottom_share),
            )
        )
    return result


def _option_note(
    is_correct: bool,
    n: int,
    share: float,
    top_share: float | None,
    bottom_share: float | None,
) -> str | None:
    if n < MIN_COHORT:
        return None
    if is_correct:
        # برابری (مثلاً همه درست زده‌اند) نشانهٔ کلید غلط نیست؛ فقط برتریِ روشنِ ضعیف‌ها.
        if (
            top_share is not None
            and bottom_share is not None
            and bottom_share - top_share >= ATTRACTS_STRONG_GAP
        ):
            return "گروه ضعیف گزینهٔ درست را بیشتر از گروه قوی زده؛ کلید سؤال را دوباره ببینید."
        return None
    if top_share is not None and bottom_share is not None:
        if top_share - bottom_share >= ATTRACTS_STRONG_GAP:
            return (
                "قوی‌ترها این گزینه را بیشتر از ضعیف‌ترها زده‌اند؛ شاید گزینه دوپهلوست یا کلید اشتباه."
            )
    if share < DEAD_OPTION_SHARE:
        return "تقریباً هیچ‌کس این گزینه را نزده؛ فریبندگی ندارد و می‌شود عوضش کرد."
    return None


def _alpha_band(alpha: float) -> tuple[str, str | None]:
    if alpha >= 0.9:
        return "عالی", None
    if alpha >= 0.8:
        return "خوب", None
    if alpha >= 0.7:
        return "قابل‌قبول", None
    if alpha >= 0.6:
        return (
            "ضعیف",
            "نمرهٔ این آزمون برای تصمیم‌های مهم (مثل قبولی) دقت کافی ندارد؛ "
            "سؤال‌های بی‌تمیز را اصلاح یا سؤال بیشتری اضافه کنید.",
        )
    return (
        "نامطمئن",
        "سؤال‌ها با هم یک چیز را نمی‌سنجند یا آزمون خیلی کوتاه است؛ به نمرهٔ کل تکیهٔ زیادی نکنید.",
    )


def _variance(values: Sequence[float]) -> float:
    """واریانس نمونه (n−1)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = math.fsum(values) / n
    return math.fsum((v - mean) ** 2 for v in values) / (n - 1)


__all__ = [
    "ATTRACTS_STRONG_GAP",
    "DEAD_OPTION_SHARE",
    "GROUP_RATIO",
    "HISTOGRAM_BINS",
    "MIN_COHORT",
    "OptionStat",
    "Reliability",
    "ScoreSummary",
    "cronbach_alpha",
    "item_rest_correlation",
    "option_stats",
    "reliability",
    "summarize_scores",
]
