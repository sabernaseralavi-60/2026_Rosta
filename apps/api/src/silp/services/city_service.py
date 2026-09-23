"""آزمایشگاه شهر هوشمند — FR-CITY-01، §7.9، M7-09، ADR-0016.

الگو خودش محتوای کد است (`silp.domain.city`)؛ این سرویس آن را به پروژه،
مرحله و تحویل‌دادنی می‌بندد:

* **ساخت** — پروژهٔ نوع C با `workflow = 'CITY'` هشت مرحلهٔ ثابت می‌گیرد،
  مسئول همه ابتدا مدیر پروژه است.
* **تحویل** — مرحلهٔ n فقط پس از تأیید n−۱ تحویل می‌پذیرد؛ شاهد
  ساختاریافته پیش از ساخت ردیف سنجیده می‌شود و فایل‌های مدل نسخه می‌خورند.
* **تأیید** — مرحلهٔ ۳ بی‌شاهد تصویری تأیید نمی‌شود؛ تأیید مرحلهٔ آخر
  گردش‌کار را کامل می‌کند.
* **کتابخانه** — همهٔ پیوست‌های پروژه برای اعضا و بازبین‌ها قابل دانلود.

این سرویس `ProjectService` و `DeliveryService` را وارد نمی‌کند؛ آن دو
این را وارد می‌کنند.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    CityStageLocked,
    Conflict,
    NotFound,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser
from silp.domain import city as rules
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.text import to_persian_digits
from silp.models.delivery import (
    Deliverable,
    DeliverableFile,
    Milestone,
    ProjectArtifactVersion,
    ProjectMessage,
)
from silp.models.file import File
from silp.models.project import Project, Team, TeamMember
from silp.services import events

log = get_logger("silp.city")

#: پروژه‌هایی که محدوده‌شان در سنجش هم‌پوشانی حساب می‌شود.
ACTIVE_PROJECT_STATUSES = ("DRAFT", "OPEN", "IN_PROGRESS", "PAUSED")
#: تحویل‌هایی که محدوده‌شان «ادعای زنده» است — ردشده حساب نیست.
LIVE_DELIVERABLE_STATUSES = ("SUBMITTED", "UNDER_REVIEW", "APPROVED")
#: پروژه‌های شهری که در صفحهٔ عمومی آزمایشگاه دیده می‌شوند.
PUBLIC_PROJECT_STATUSES = ("OPEN", "IN_PROGRESS", "PAUSED", "COMPLETED")


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AreaView:
    geometry: dict[str, Any]
    area_km2: float
    bbox: list[float]
    approved: bool


@dataclass(slots=True)
class LibraryEntry:
    file: File
    source: str
    milestone: Milestone | None = None
    deliverable: Deliverable | None = None
    attached_at: datetime | None = None
    attached_by: uuid.UUID | None = None


@dataclass(slots=True)
class ArtifactHistory:
    artifact: str
    versions: list[tuple[ProjectArtifactVersion, File, Deliverable, Milestone]] = field(
        default_factory=list
    )

    @property
    def current(self) -> ProjectArtifactVersion | None:
        """آخرین نسخهٔ تأییدشده — «نسخهٔ جاری» مدل."""
        approved = [v for v, _, d, _ in self.versions if d.status == "APPROVED"]
        return max(approved, key=lambda v: v.version) if approved else None


class CityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── ساخت ───────────────────────────────────────────────────────────
    async def apply_workflow(self, project: Project, *, starts_on: Any = None) -> list[Milestone]:
        """هشت مرحلهٔ الگو، بدون commit — فراخوان تراکنش را می‌بندد."""
        existing = await self.session.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(Milestone.project_id == project.id, Milestone.workflow_stage.is_not(None))
        )
        if existing:
            raise Conflict("الگوی گردش‌کار این پروژه قبلاً اعمال شده است.")
        dues = rules.due_dates(starts_on)
        milestones = [
            Milestone(
                project_id=project.id,
                title_fa=spec.title_fa,
                description=spec.deliverable_fa,
                sort_order=spec.number,
                due_on=dues[spec.number],
                points=Decimal(spec.points),
                is_required=True,
                output_kind=spec.output_kind,
                checklist=[item.text for item in spec.checklist],
                status="IN_PROGRESS" if project.status == "IN_PROGRESS" else "PENDING",
                workflow_stage=spec.number,
                owner_id=project.lead_id,
            )
            for spec in rules.STAGES
        ]
        self.session.add_all(milestones)
        project.workflow = rules.WORKFLOW_CITY
        await self.session.flush()
        return milestones

    # ── وضعیت ──────────────────────────────────────────────────────────
    async def stage_milestones(self, project_id: uuid.UUID) -> dict[int, Milestone]:
        rows = await self.session.scalars(
            select(Milestone).where(
                Milestone.project_id == project_id, Milestone.workflow_stage.is_not(None)
            )
        )
        return {m.workflow_stage: m for m in rows if m.workflow_stage is not None}

    async def stage_statuses(self, project_id: uuid.UUID) -> dict[int, str]:
        return {n: m.status for n, m in (await self.stage_milestones(project_id)).items()}

    # ── تحویل ──────────────────────────────────────────────────────────
    async def check_submission(
        self,
        *,
        milestone: Milestone,
        project: Project,
        body: str | None,
        links: list[str],
        file_ids: list[uuid.UUID],
        evidence: dict[str, Any] | None,
        checklist_confirmed: list[int] | None,
    ) -> dict[str, Any]:
        """قفل مرحله، سپس شاهد. خروجی: شاهد پاک‌شده برای `deliverables.evidence`.

        قفل پیش از شاهد: مرحلهٔ قفل باید «قفل» بگوید، نه فهرست کمبودها —
        همان ترتیب مسیر پژوهش (ADR-0015).
        """
        number = milestone.workflow_stage
        assert number is not None
        statuses = await self.stage_statuses(project.id)
        if rules.is_locked(number, statuses):
            previous = rules.stage(number - 1)
            raise CityStageLocked(
                f"«{milestone.title_fa}» پس از تأیید مرحلهٔ"
                f" {to_persian_digits(previous.number)} («{previous.title_fa}») باز می‌شود.",
                details={"blocked_by": previous.number},
            )

        files = await self._attached(file_ids)
        cleaned, problems = rules.validate_submission(
            number,
            body=body,
            links=links,
            files=files,
            evidence=evidence or {},
            checklist_confirmed=checklist_confirmed or [],
            today=_now().astimezone(LOCAL_TZ).date(),
        )
        if problems:
            raise ValidationFailed(
                "تحویل کامل نیست: " + "؛ ".join(problems) + ".",
                details={"missing": problems},
            )
        if rules.stage(number).structured == "AREA":
            cleaned["overlaps"] = await self._overlaps(project, cleaned["area"])
        return cleaned

    async def record_artifacts(
        self, *, project: Project, deliverable: Deliverable, file_ids: list[uuid.UUID]
    ) -> list[ProjectArtifactVersion]:
        """هر فایل مدلِ این تحویل، نسخهٔ بعدی همان نوع در کتابخانه.

        ردیف پروژه قفل می‌شود تا دو تحویل هم‌زمان یک شماره نگیرند (§7.12)؛
        تحویل مرحلهٔ ۲ و ۴ کم است و این قفل کوتاه.
        """
        found = rules.artifacts_in(await self._attached(file_ids))
        if not found:
            return []
        await self.session.execute(
            select(Project.id).where(Project.id == project.id).with_for_update()
        )
        created: list[ProjectArtifactVersion] = []
        for artifact, file in found.items():
            latest = await self.session.scalar(
                select(func.coalesce(func.max(ProjectArtifactVersion.version), 0)).where(
                    ProjectArtifactVersion.project_id == project.id,
                    ProjectArtifactVersion.artifact == artifact,
                )
            )
            row = ProjectArtifactVersion(
                project_id=project.id,
                artifact=artifact,
                version=int(latest or 0) + 1,
                file_id=uuid.UUID(file.id),
                deliverable_id=deliverable.id,
                created_by=deliverable.submitter_id,
            )
            self.session.add(row)
            created.append(row)
        await self.session.flush()
        return created

    # ── تأیید ──────────────────────────────────────────────────────────
    async def guard_approval(self, *, milestone: Milestone, deliverable: Deliverable) -> None:
        """§7.9 — «راستی‌آزمایی OSM بدون شواهد تصویری تأیید نمی‌شود».

        تحویل بی‌تصویر از همان ابتدا پذیرفته نمی‌شود؛ این نگهبان برای
        داده‌ای است که از راه دیگری رسیده باشد — دفاع در عمق.
        """
        if milestone.workflow_stage != 3:
            return
        images = await self.session.scalar(
            select(func.count())
            .select_from(DeliverableFile)
            .join(File, File.id == DeliverableFile.file_id)
            .where(
                DeliverableFile.deliverable_id == deliverable.id,
                File.content_type.like("image/%"),
                File.deleted_at.is_(None),
            )
        )
        if not images or rules.image_count(deliverable.evidence) == 0:
            raise Conflict(
                "راستی‌آزمایی بدون شواهد تصویری تأیید نمی‌شود؛ «اصلاح کن» را بزن و"
                " تصویرها را بخواه.",
                code="CITY_EVIDENCE_MISSING",
            )

    async def after_approval(self, *, project: Project) -> bool:
        """اگر هر هشت مرحله تأیید شده باشد، گردش‌کار کامل است. خروجی: همین حالا کامل شد؟"""
        if project.workflow != rules.WORKFLOW_CITY or project.workflow_completed_at is not None:
            return False
        await self.session.flush()
        statuses = await self.stage_statuses(project.id)
        if rules.current_stage(statuses) is not None or len(statuses) < rules.STAGE_COUNT:
            return False
        project.workflow_completed_at = _now()
        await events.publish(self.session, events.CityWorkflowCompleted(project_id=project.id))
        log.info("city_workflow_completed", project_id=str(project.id))
        return True

    # ── مسئول مرحله ────────────────────────────────────────────────────
    async def assign_owner(
        self,
        *,
        milestone: Milestone,
        project: Project,
        owner_id: uuid.UUID | None,
        actor: CurrentUser,
    ) -> Milestone:
        if milestone.status == "APPROVED":
            raise Conflict("مسئول مرحلهٔ تأییدشده عوض نمی‌شود؛ بخشی از تاریخچهٔ پروژه است.")
        if owner_id is None:
            if milestone.workflow_stage is not None:
                raise ValidationFailed("هر مرحلهٔ گردش‌کار شهری مسئول دارد.")
        elif owner_id != project.lead_id and not await self._is_active_member(project.id, owner_id):
            raise ValidationFailed("مسئول مرحله باید عضو فعال تیم باشد.")
        if milestone.owner_id == owner_id:
            return milestone
        milestone.owner_id = owner_id
        project.last_activity_at = _now()
        if owner_id is not None:
            await events.publish(
                self.session,
                events.MilestoneOwnerAssigned(milestone_id=milestone.id, assigned_by=actor.id),
            )
        await self.session.commit()
        return milestone

    async def release_ownership(self, project: Project, user_id: uuid.UUID) -> None:
        """عضوی که رفت، مسئول مرحلهٔ باز نمی‌ماند؛ مسئولیت به مدیر برمی‌گردد."""
        rows = await self.session.scalars(
            select(Milestone).where(
                Milestone.project_id == project.id,
                Milestone.owner_id == user_id,
                Milestone.status != "APPROVED",
            )
        )
        for milestone in rows:
            milestone.owner_id = project.lead_id

    # ── نمای پروژه ─────────────────────────────────────────────────────
    async def area_of(self, project_id: uuid.UUID) -> AreaView | None:
        """محدودهٔ پروژه — تحویل تأییدشدهٔ مرحلهٔ ۱، وگرنه آخرین تحویل زنده."""
        rows = await self.session.scalars(
            select(Deliverable)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(
                Milestone.project_id == project_id,
                Milestone.workflow_stage == 1,
                Deliverable.status.in_(LIVE_DELIVERABLE_STATUSES),
                Deliverable.evidence.is_not(None),
            )
            .order_by(Deliverable.submitted_at.desc())
        )
        candidates = list(rows)
        chosen = next((d for d in candidates if d.status == "APPROVED"), None) or next(
            iter(candidates), None
        )
        if chosen is None or not chosen.evidence or "area" not in chosen.evidence:
            return None
        ev = chosen.evidence
        return AreaView(
            geometry=ev["area"],
            area_km2=float(ev.get("area_km2") or 0),
            bbox=list(ev.get("bbox") or []),
            approved=chosen.status == "APPROVED",
        )

    async def artifact_histories(self, project_id: uuid.UUID) -> list[ArtifactHistory]:
        rows = await self.session.execute(
            select(ProjectArtifactVersion, File, Deliverable, Milestone)
            .join(File, File.id == ProjectArtifactVersion.file_id)
            .join(Deliverable, Deliverable.id == ProjectArtifactVersion.deliverable_id)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(ProjectArtifactVersion.project_id == project_id)
            .order_by(ProjectArtifactVersion.artifact, ProjectArtifactVersion.version.desc())
        )
        by_kind = {kind: ArtifactHistory(kind) for kind in rules.ARTIFACTS}
        for version, file, deliverable, milestone in rows.tuples():
            by_kind[version.artifact].versions.append((version, file, deliverable, milestone))
        return list(by_kind.values())

    async def library(self, project_id: uuid.UUID) -> list[LibraryEntry]:
        """کتابخانهٔ فایل پروژه — FR-PRJ-06: پیوست تحویل‌ها و پیام‌ها، تازه‌ترین اول."""
        entries: list[LibraryEntry] = []
        delivered = await self.session.execute(
            select(File, Deliverable, Milestone)
            .join(DeliverableFile, DeliverableFile.file_id == File.id)
            .join(Deliverable, Deliverable.id == DeliverableFile.deliverable_id)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(Milestone.project_id == project_id, File.deleted_at.is_(None))
        )
        for file, deliverable, milestone in delivered.tuples():
            entries.append(
                LibraryEntry(
                    file=file,
                    source="DELIVERABLE",
                    milestone=milestone,
                    deliverable=deliverable,
                    attached_at=deliverable.submitted_at,
                    attached_by=deliverable.submitter_id,
                )
            )
        messaged = await self.session.execute(
            select(File, ProjectMessage)
            .join(ProjectMessage, ProjectMessage.file_id == File.id)
            .where(
                ProjectMessage.project_id == project_id,
                ProjectMessage.deleted_at.is_(None),
                File.deleted_at.is_(None),
            )
        )
        for file, message in messaged.tuples():
            entries.append(
                LibraryEntry(
                    file=file,
                    source="MESSAGE",
                    attached_at=message.created_at,
                    attached_by=message.author_id,
                )
            )
        entries.sort(key=lambda e: e.attached_at or _now(), reverse=True)
        return entries

    async def project_file(self, project_id: uuid.UUID, file_id: uuid.UUID) -> File:
        """فایلی که واقعاً به این پروژه پیوست شده — وگرنه ۴۰۴ (§6.4 قاعدهٔ ۴)."""
        in_deliverable = (
            select(DeliverableFile.file_id)
            .join(Deliverable, Deliverable.id == DeliverableFile.deliverable_id)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(Milestone.project_id == project_id, DeliverableFile.file_id == file_id)
        )
        in_message = select(ProjectMessage.file_id).where(
            ProjectMessage.project_id == project_id,
            ProjectMessage.file_id == file_id,
            ProjectMessage.deleted_at.is_(None),
        )
        file = await self.session.scalar(
            select(File).where(
                File.id == file_id,
                File.deleted_at.is_(None),
                or_(File.id.in_(in_deliverable), File.id.in_(in_message)),
            )
        )
        if file is None:
            raise NotFound("فایل پیدا نشد.")
        return file

    async def public_projects(self) -> list[tuple[Project, dict[int, str], AreaView | None]]:
        """پروژه‌های شهری صفحهٔ آزمایشگاه — پیش‌نویس و لغوشده بیرون‌اند."""
        projects = list(
            await self.session.scalars(
                select(Project)
                .where(
                    Project.workflow == rules.WORKFLOW_CITY,
                    Project.deleted_at.is_(None),
                    Project.status.in_(PUBLIC_PROJECT_STATUSES),
                )
                .order_by(Project.created_at.desc())
                .limit(50)
            )
        )
        if not projects:
            return []
        rows = await self.session.execute(
            select(Milestone.project_id, Milestone.workflow_stage, Milestone.status).where(
                Milestone.project_id.in_([p.id for p in projects]),
                Milestone.workflow_stage.is_not(None),
            )
        )
        statuses: dict[uuid.UUID, dict[int, str]] = {}
        for project_id, stage, status in rows.tuples():
            if stage is not None:
                statuses.setdefault(project_id, {})[int(stage)] = status
        result = []
        for project in projects:
            result.append((project, statuses.get(project.id, {}), await self.area_of(project.id)))
        return result

    # ── درونی ──────────────────────────────────────────────────────────
    async def _attached(self, file_ids: list[uuid.UUID]) -> list[rules.AttachedFile]:
        if not file_ids:
            return []
        rows = await self.session.scalars(select(File).where(File.id.in_(file_ids)))
        return [
            rules.AttachedFile(id=str(f.id), name=f.original_name, content_type=f.content_type)
            for f in rows
        ]

    async def _overlaps(self, project: Project, geometry: dict[str, Any]) -> list[dict[str, str]]:
        """هم‌پوشانی با محدودهٔ پروژه‌های شهری فعال دیگر — هشدار، نه ممنوعیت (FR-CITY-02)."""
        mine = rules.polygons_of(geometry)
        rows = await self.session.execute(
            select(Project.id, Project.title_fa, Deliverable.evidence)
            .join(Milestone, Milestone.project_id == Project.id)
            .join(Deliverable, Deliverable.milestone_id == Milestone.id)
            .where(
                Project.workflow == rules.WORKFLOW_CITY,
                Project.id != project.id,
                Project.deleted_at.is_(None),
                Project.status.in_(ACTIVE_PROJECT_STATUSES),
                Milestone.workflow_stage == 1,
                Deliverable.status.in_(LIVE_DELIVERABLE_STATUSES),
                Deliverable.evidence.is_not(None),
            )
            .order_by(Deliverable.submitted_at.desc())
        )
        seen: set[uuid.UUID] = set()
        overlaps: list[dict[str, str]] = []
        for other_id, title, evidence in rows.tuples():
            if other_id in seen:
                continue
            seen.add(other_id)  # فقط تازه‌ترین محدودهٔ هر پروژه
            theirs = rules.polygons_of((evidence or {}).get("area"))
            if theirs and rules.polygons_overlap(mine, theirs):
                overlaps.append({"project_id": str(other_id), "title_fa": title})
        return overlaps

    async def _is_active_member(self, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.project_id == project_id,
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
            )
        )
        return found is not None


__all__ = ["ArtifactHistory", "AreaView", "CityService", "LibraryEntry"]
