"""آزمون پوشش بانک پروژه — §14.5، M7-16.

«برای هر یک از پنج پرسونای §01، حداقل سه پروژه باید امتیاز تطابق بالای
۷۰ بگیرند. این را پیش از راه‌اندازی بررسی کنید.»

اجرا: ``python -m silp.scripts.check_coverage`` — خروج غیرصفر یعنی رد.

به دیتابیس دست نمی‌زند: پرسوناها و بانک هر دو داده‌اند و امتیاز با همان
`score_project` موتور توصیه‌گر حساب می‌شود. کدها با `uuid5` به شناسه
تبدیل می‌شوند، پس نتیجه در هر محیطی یکسان است و در CI هم اجرا می‌شود
(`tests/unit/test_project_bank.py`).

پرسونای ۴ §01 استاد است و پروژه برنمی‌دارد. جایش «دانشجوی غیرفنی بی‌وسیله
و کم‌وقت» نشسته — همان دانشجویی که قواعد توزیع §14.5 برایش نوشته شده‌اند
(ADR-0018).
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from silp.content.project_bank import PROJECTS, ProjectSeed
from silp.domain.recommendation.schemas import (
    AssetReq,
    Goal,
    InterestRef,
    ProjectKind,
    ProjectSpec,
    SkillReq,
    StudentContext,
    WorkStyle,
)
from silp.domain.recommendation.scorer import score_project

THRESHOLD = 70.0
REQUIRED_MATCHES = 3

_NAMESPACE = uuid.UUID("5b1c9a7e-0d4e-4c55-9a51-7c1f8f0a2d18")


def _id(kind: str, code: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{kind}:{code}")


@dataclass(frozen=True, slots=True)
class Persona:
    key: str
    title_fa: str
    goal: Goal
    work_style: WorkStyle
    weekly_hours: int
    skills: dict[str, int] = field(default_factory=dict)
    assets: tuple[str, ...] = ()
    interests: dict[str, int] = field(default_factory=dict)

    def context(self) -> StudentContext:
        return StudentContext(
            user_id=_id("persona", self.key),
            skills={_id("skill", c): level for c, level in self.skills.items()},
            assets=frozenset(_id("asset", c) for c in self.assets),
            interests={_id("interest", c): level for c, level in self.interests.items()},
            weekly_hours=self.weekly_hours,
            work_style=self.work_style,
            primary_goal=self.goal,
            completed_steps=4,
        )


# §01 — مهارت‌ها از جدول هر پرسونا: «متوسط» ۳، «خوب» ۴، «قوی» ۵، «مبتدی» ۲.
PERSONAS: tuple[Persona, ...] = (
    Persona(
        "maryam",
        "مریم — دانشجوی درس (هدف نمره)",
        Goal.GRADE,
        WorkStyle.TEAM,
        8,
        skills={"EXCEL": 3, "AUTOCAD": 4, "PYTHON": 2, "ENGLISH": 3},
        assets=("LAPTOP", "FAST_INTERNET"),
        interests={"TRANSPORT": 4, "URBAN": 4, "DATA_ANALYSIS": 3, "PROJECT_MGMT": 3},
    ),
    Persona(
        "amir",
        "امیر — دانشجوی پژوهشی (هدف مقاله)",
        Goal.PUBLICATION,
        WorkStyle.SOLO,
        14,
        skills={"R": 5, "PYTHON": 4, "STATISTICS": 4, "WRITING": 3, "ENGLISH": 2},
        assets=("LAPTOP", "POWERFUL_PC", "FAST_INTERNET"),
        interests={"RESEARCH": 5, "DATA_ANALYSIS": 5, "TRANSPORT": 4},
    ),
    Persona(
        "sara",
        "سارا — کارآفرین دانشجو (هدف درآمد)",
        Goal.INCOME,
        WorkStyle.TEAM,
        12,
        skills={"MARKETING_SKILL": 4, "PRESENTATION": 4, "GRAPHIC_DESIGN": 3},
        assets=("LAPTOP", "MOTORCYCLE", "CAMERA"),
        interests={"SALES": 5, "MARKETING": 5, "CONTENT": 5, "COMMERCE": 4},
    ),
    Persona(
        "reza",
        "رضا — کاربر عمومی، کارشناس شهرداری (یادگیری SUMO)",
        Goal.LEARNING,
        WorkStyle.SOLO,
        5,
        skills={"EXCEL": 3, "GIS": 2, "ENGLISH": 2},
        assets=("LAPTOP",),
        interests={"TRANSPORT": 5, "URBAN": 5, "PROGRAMMING": 3},
    ),
    Persona(
        "nontech",
        "دانشجوی غیرفنی، بی‌وسیله و کم‌وقت (به‌جای پرسونای استاد)",
        Goal.LEARNING,
        WorkStyle.EITHER,
        4,
        skills={"WRITING": 3, "PRESENTATION": 3, "ENGLISH": 2},
        assets=("LAPTOP",),
        interests={"URBAN": 4, "CONTENT": 4, "RESEARCH": 3},
    ),
)


def project_spec(seed: ProjectSeed) -> ProjectSpec:
    return ProjectSpec(
        id=_id("project", seed.slug),
        title_fa=seed.title_fa,
        kind=ProjectKind(seed.kind),
        difficulty=seed.difficulty,
        work_style=WorkStyle(seed.work_style),
        time_commitment_hpw=seed.time_commitment_hpw,
        team_size_min=seed.team_size_min,
        team_size_max=seed.team_size_max,
        required_skills=tuple(
            SkillReq(_id("skill", s.code), s.code, s.min_level, s.weight, s.teachable)
            for s in seed.skills
        ),
        required_assets=tuple(
            AssetReq(_id("asset", a.code), a.code, a.mandatory) for a in seed.assets
        ),
        interests=tuple(InterestRef(_id("interest", c), c) for c in seed.interests),
    )


def coverage(
    projects: tuple[ProjectSeed, ...] = PROJECTS,
    personas: tuple[Persona, ...] = PERSONAS,
) -> dict[str, list[tuple[str, float]]]:
    """برای هر پرسونا: پروژه‌های بالای آستانه، از بیشترین امتیاز."""
    now = datetime(2026, 9, 23, tzinfo=UTC)
    specs = [project_spec(p) for p in projects]
    result: dict[str, list[tuple[str, float]]] = {}
    for persona in personas:
        ctx = persona.context()
        matches = []
        for spec in specs:
            match = score_project(ctx, spec, now=now)
            if not match.is_excluded and match.score > THRESHOLD:
                matches.append((spec.title_fa, round(match.score, 1)))
        result[persona.key] = sorted(matches, key=lambda m: -m[1])
    return result


def main() -> int:
    result = coverage()
    failed = False
    print("\nپوشش بانک پروژه — §14.5\n")
    for persona in PERSONAS:
        matches = result[persona.key]
        ok = len(matches) >= REQUIRED_MATCHES
        failed |= not ok
        print(f"  {'قبول' if ok else 'رد  '}  {persona.title_fa}: {len(matches)} پروژه بالای ۷۰")
        for title, score in matches[:5]:
            print(f"          {score:5.1f}  {title}")
    print("")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
