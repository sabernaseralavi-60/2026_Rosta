"""مدیریت الگوهای پیام — FR-MSG-03، M6-10.

* ویرایش الگو با متغیر ناشناخته رد می‌شود (`templating.validate`).
* الگوی `IN_APP` هر نوع اعلان غیرفعال‌شدنی نیست: مرکز اعلان بدون آن
  چیزی برای نمایش ندارد و `notify` شکست می‌خورد.
* «پیش‌نمایش پیش از ذخیره» با مقدارهای نمونهٔ فارسی — مدیر می‌بیند
  پیامک واقعاً چند بخش می‌شود.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings, get_settings
from silp.core.exceptions import NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.domain.notifications import catalog
from silp.domain.notifications.templating import (
    Rendered,
    TemplateError,
    render,
    sms_parts,
    validate,
)
from silp.models.messaging import MessageTemplate

log = get_logger("silp.templates")

#: مقدار نمونهٔ متغیرها برای پیش‌نمایش — واقع‌نما، تا طول پیامک درست دیده شود.
SAMPLE_VALUES: dict[str, str] = {
    "name": "مریم",
    "course": "برنامه‌ریزی حمل‌ونقل",
    "student": "مریم کریمی",
    "applicant": "مریم کریمی",
    "submitter": "مریم کریمی",
    "project": "مدل‌سازی SUMO محور اصلی کرمان",
    "milestone": "گزارش مرور ادبیات",
    "points": "۵۰",
    "days": "۳",
    "due_on": "۹ مهر",
    "closes_at": "۹ مهر، ساعت ۱۸:۰۰",
    "week": "۴",
    "title": "تحلیل تقاضای سفر",
    "quiz": "آزمون هفتهٔ ۴",
    "score": "۱۷",
    "total": "۲۰",
    "outcome": "پذیرفته شد",
    "reason": "ظرفیت تیم تکمیل شد.",
    "feedback": "بخش روش‌شناسی را با جزئیات بیشتری بنویس.",
    "excerpt": "جلسهٔ فردا به‌جای کلاس ۲۰۴ در آزمایشگاه برگزار می‌شود.",
    "badge": "شروع سریع",
    "channel": "تلگرام",
    "unread": "۴",
    "deadlines": "۲",
    "reviews": "۶",
    "enrollments": "۳",
    "at_risk": "۱",
    "count": "۱۲",
    "code": "۴۸۲۹۱۷",
    "idea": "اپلیکیشن اشتراک خودرو برای دانشجویان",
    "commenter": "علی احمدی",
    "target": "پروژه",
    "next_step": "دعوت پیوستن به تیمش برایت فرستاده شد.",
    "inviter": "مریم کریمی",
    "invitee": "علی احمدی",
    "team": "خرمای صابر",
    "message": "به مهارت GIS تو نیاز داریم.",
    "metric": "مبلغ فروش",
    "value": "۱۲٬۰۰۰٬۰۰۰ ریال",
    "owner": "خرمای صابر",
    "decision": "تأیید شد",
    "detail": "۲٫۴ امتیاز کارآفرینی گرفتی.",
    "venture": "خرمای صابر",
    "stage": "محصول کمینه",
    "from_stage": "اعتبارسنجی",
    "level": "۲ (تحلیل داده)",
    "topic": "ایمنی عابر پیاده در تقاطع‌های کرمان",
    "opening": "تحلیلگر GIS",
    "skills": "GIS و Python",
    "assigner": "مریم کریمی",
    "number": "۴",
}


class TemplateService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def all(self) -> list[MessageTemplate]:
        rows = await self.session.scalars(
            select(MessageTemplate).order_by(MessageTemplate.code, MessageTemplate.channel)
        )
        return list(rows)

    async def update(
        self,
        *,
        code: str,
        channel: str,
        subject: str | None,
        body: str,
        is_active: bool,
        actor_id: uuid.UUID,
    ) -> MessageTemplate:
        allowed = self._allowed(code)
        if channel not in catalog.CHANNELS:
            raise NotFound("این کانال وجود ندارد.")
        if channel == "IN_APP" and code in catalog.KINDS and not is_active:
            raise ValidationFailed("الگوی داخلی یک نوع اعلان را نمی‌توان غیرفعال کرد.")
        if channel == "SMS" and code in catalog.KINDS and not catalog.KINDS[code].allow_sms:
            raise ValidationFailed("این نوع اعلان پیامک نمی‌شود؛ الگوی پیامک برایش بی‌اثر است.")
        cleaned_subject = (subject or "").strip() or None
        try:
            validate(cleaned_subject, body, allowed)
        except TemplateError as exc:
            raise ValidationFailed(str(exc), code="TEMPLATE_INVALID") from exc

        statement = insert(MessageTemplate).values(
            code=code,
            channel=channel,
            subject=cleaned_subject,
            body=body.strip(),
            variables=list(allowed),
            is_active=is_active,
            updated_by=actor_id,
        )
        row = await self.session.scalar(
            statement.on_conflict_do_update(
                index_elements=["code", "channel"],
                set_={
                    "subject": statement.excluded.subject,
                    "body": statement.excluded.body,
                    "variables": statement.excluded.variables,
                    "is_active": statement.excluded.is_active,
                    "updated_by": statement.excluded.updated_by,
                },
            ).returning(MessageTemplate)
        )
        await self.session.commit()
        assert row is not None
        log.info("template_updated", code=code, channel=channel, actor=str(actor_id))
        return row

    def preview(
        self,
        *,
        code: str,
        channel: str,
        subject: str | None,
        body: str,
        values: Mapping[str, str] | None = None,
    ) -> tuple[Rendered, int | None]:
        allowed = self._allowed(code)
        cleaned_subject = (subject or "").strip() or None
        try:
            validate(cleaned_subject, body, allowed)
            sample = {name: SAMPLE_VALUES.get(name, name) for name in allowed}
            sample["link"] = f"{self.settings.frontend_url.rstrip('/')}/dashboard"
            sample.update({k: v for k, v in (values or {}).items() if k in allowed})
            rendered = render(cleaned_subject, body, sample)
        except TemplateError as exc:
            raise ValidationFailed(str(exc), code="TEMPLATE_INVALID") from exc
        return rendered, sms_parts(rendered.body) if channel == "SMS" else None

    @staticmethod
    def _allowed(code: str) -> tuple[str, ...]:
        try:
            return catalog.template_variables(code)
        except ValueError as exc:
            raise NotFound("این الگو وجود ندارد.") from exc


__all__ = ["SAMPLE_VALUES", "TemplateService"]
