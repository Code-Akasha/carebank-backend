from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.models import TransactionResponse, TransactionTriggerCreate
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _persist_transactions(db: Session, records: list[dict]) -> None:
    if not records:
        return
    for record in records:
        existing = db.get(Transaction, record["id"])
        if existing:
            existing.amount = record["amount"]
            existing.date = record["date"]
            existing.merchant = record.get("merchant")
            existing.category = record.get("category")
            existing.description = record.get("description")
        else:
            db.add(
                Transaction(
                    id=record["id"],
                    user_id=record["user_id"],
                    amount=record["amount"],
                    date=record["date"],
                    merchant=record.get("merchant"),
                    category=record.get("category"),
                    description=record.get("description"),
                ),
            )
    db.commit()


@router.get("/")
async def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    client = get_banking_client()
    try:
        records = await client.get_transactions(
            current_user.user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    _persist_transactions(db, records)

    result = [
        TransactionResponse(
            id=record["id"],
            user_id=record["user_id"],
            amount=record["amount"],
            merchant=record.get("merchant"),
            category=record.get("category"),
            description=record.get("description"),
            date=record["date"],
        )
        for record in records
    ]

    return {"transactions": result[:limit], "total": len(result)}


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    txn = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.user_id == current_user.user_id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.post("/trigger", response_model=dict)
async def trigger_transaction_proxy(
    payload: TransactionTriggerCreate,
    current_user: Annotated[User, Depends(get_current_user)],
):
    # Ensure user can only trigger for themselves
    payload_dict = payload.model_dump()
    payload_dict["user_id"] = current_user.user_id

    # Set defaults for merchant and category if not provided
    if not payload_dict.get("merchant"):
        payload_dict["merchant"] = "Manual Transaction"
    if not payload_dict.get("category"):
        payload_dict["category"] = "Manual"

    client = get_banking_client()
    try:
        response = await client.trigger_transaction(payload_dict)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc
    return response
