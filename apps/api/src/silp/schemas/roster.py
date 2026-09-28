"""مدل‌های ورود دانشجوی درس — ADR-0035."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, Field

from silp.schemas.auth import LoginOut


class RosterLookupIn(BaseModel):
    mobile: Annotated[str, Field(min_length=1, max_length=32)]
    student_no: Annotated[str, Field(min_length=1, max_length=32)]


class RosterLookupOut(BaseModel):
    claim_id: uuid.UUID
    #: «علی ا.» — نام کامل پیش از تأیید هویت نشان داده نمی‌شود.
    display_name: str
    has_email: bool


class RosterConfirmIn(BaseModel):
    claim_id: uuid.UUID
    accept: bool


class RosterConfirmOut(BaseModel):
    cancelled: bool
    masked_email: str | None = None
    expires_in: int = 0
    resend_after: int = 0


class RosterCompleteIn(BaseModel):
    claim_id: uuid.UUID
    code: Annotated[str, Field(min_length=4, max_length=10)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class RosterCompleteOut(LoginOut):
    #: نادرست یعنی دانشجوی برگشتی بود (حسابش هست؛ درس‌های تازه اضافه شد).
    is_new_user: bool
    courses: list[str]
