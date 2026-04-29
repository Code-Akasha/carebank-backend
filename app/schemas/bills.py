from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class BillCandidateResponse(BaseModel):
    source_type: str
    source_id: int
    recurring_rule_id: int | None = None
    title: str
    category: str | None = None
    amount: float | None = None
    due_date: date
    action_type: str
    metadata: dict[str, Any] | None = None
