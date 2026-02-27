from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.balance import Balance
from app.schemas.models import BalanceResponse

router = APIRouter(prefix="/api/balances", tags=["balances"])


@router.get("/{user_id}", response_model=BalanceResponse)
def get_balance(user_id: str, db: Session = Depends(get_db)):
    balance = db.query(Balance).filter(Balance.user_id == user_id).first()
    if not balance:
        raise HTTPException(status_code=404, detail="Balance not found")
    return balance
