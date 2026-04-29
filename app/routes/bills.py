from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.bills import BillCandidateResponse
from app.services.bill_discovery import discover_bill_candidates

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("/discover", response_model=list[BillCandidateResponse])
def discover_bills(
    current_user: Annotated[User, Depends(get_current_user)],
    action_type: str = "pay_bill",
    checklist_horizon_days: int = 7,
    rule_horizon_days: int = 35,
    limit: int = 8,
    db: Session = Depends(get_db),
):
    normalized_type = (action_type or "").strip().lower()
    safe_limit = max(1, min(int(limit), 50))
    safe_checklist_days = max(1, min(int(checklist_horizon_days), 60))
    safe_rule_days = max(1, min(int(rule_horizon_days), 120))

    candidates = discover_bill_candidates(
        db,
        user_id=str(current_user.user_id),
        action_type=normalized_type,
        checklist_horizon_days=safe_checklist_days,
        rule_horizon_days=safe_rule_days,
        limit=safe_limit,
    )

    return [BillCandidateResponse(**candidate) for candidate in candidates]
