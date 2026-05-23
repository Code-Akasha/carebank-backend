"""Business billing routes — issue, list, pay, and cancel bills."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.business import BillCreate, BillPayRequest, BillResponse
from app.services.bill_service import (
    cancel_bill,
    create_bill,
    list_bills_issued,
    list_bills_received,
    pay_bill,
)

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.post("", response_model=BillResponse, status_code=201)
def issue_bill(
    body: BillCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Business issues a bill to a user."""
    result = create_bill(db, current_user.user_id, body)
    return result


@router.get("/issued", response_model=list[BillResponse])
def get_issued_bills(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """Business views bills they have issued."""
    return list_bills_issued(db, current_user.user_id, status_filter)


@router.get("/received", response_model=list[BillResponse])
def get_received_bills(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """User views bills issued to them."""
    return list_bills_received(db, current_user.user_id, status_filter)


@router.post("/{bill_id}/pay", response_model=BillResponse)
async def pay_user_bill(
    bill_id: int,
    body: BillPayRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """User pays a pending bill with MPIN verification."""
    return pay_bill(
        db,
        user_id=current_user.user_id,
        bill_id=bill_id,
        mpin=body.mpin,
        payment_method=body.payment_method,
    )


@router.post("/{bill_id}/cancel", response_model=BillResponse)
def cancel_user_bill(
    bill_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Business cancels a pending bill."""
    return cancel_bill(db, current_user.user_id, bill_id)
