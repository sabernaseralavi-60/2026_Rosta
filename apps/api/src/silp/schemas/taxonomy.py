"""مدل‌های Pydantic برای /taxonomy — قرارداد §5.4."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title_fa: str
    title_en: str
    category: str
    icon: str | None = None
    sort_order: int
    # گام ۱ فقط هسته‌ای‌ها را نشان می‌دهد؛ بقیه پشت «مهارت‌های بیشتر».
    is_core: bool


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title_fa: str
    category: str
    icon: str | None = None
    sort_order: int


class InterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title_fa: str
    icon: str | None = None
    sort_order: int


class UniversityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title_fa: str
    title_en: str | None = None
    city: str | None = None
    province: str | None = None
    type: str | None = None


class LevelLabel(BaseModel):
    """متن توصیفی هر سطح — FR-PROF-01.

    سرور این متن‌ها را می‌فرستد تا `SkillSlider` آن‌ها را در خود ثابت
    نکند؛ تعریف سطح باید در فرم و در توضیح توصیه‌گر یکی باشد.
    """

    level: int
    label: str


class SkillListOut(BaseModel):
    items: list[SkillOut]
    level_labels: list[LevelLabel]


class InterestListOut(BaseModel):
    items: list[InterestOut]
    level_labels: list[LevelLabel]


__all__ = [
    "AssetOut",
    "InterestListOut",
    "InterestOut",
    "LevelLabel",
    "SkillListOut",
    "SkillOut",
    "UniversityOut",
]
