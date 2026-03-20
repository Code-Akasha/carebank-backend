from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: int
    user_id: str
    kind: str
    title: str
    body: str
    payload: dict[str, Any] | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None


class NotificationMarkReadRequest(BaseModel):
    read: bool = Field(default=True)
