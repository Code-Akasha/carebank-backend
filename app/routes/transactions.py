from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transaction import Transaction
from app.schemas.models import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionResponse])
def list_transactions(user_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.post("/", response_model=TransactionResponse, status_code=201)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    txn = Transaction(**payload.model_dump())
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn
