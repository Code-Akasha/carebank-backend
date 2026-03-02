from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transaction import Transaction
from app.schemas.models import TransactionCreate, TransactionResponse
from app.services.banking_client import get_banking_client, BankingClientError

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
                )
            )
    db.commit()


@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    user_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    client = get_banking_client()
    try:
        records = await client.get_transactions(
            user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc

    _persist_transactions(db, records)

    return [
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


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.post("/trigger", response_model=dict)
async def trigger_transaction_proxy(payload: TransactionCreate):
    client = get_banking_client()
    try:
        response = await client.trigger_transaction(payload.model_dump())
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc
    return response
