from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.balance import Balance
from app.schemas.models import BalanceResponse
from app.services.mockbank_client import get_mockbank_client, MockBankClientError

router = APIRouter(prefix="/api/balances", tags=["balances"])


@router.get("/{user_id}", response_model=BalanceResponse)
async def get_balance(user_id: str, db: Session = Depends(get_db)):
    client = get_mockbank_client()
    try:
        balance_data = await client.get_balance(user_id)
    except MockBankClientError as exc:
        raise HTTPException(status_code=503, detail=f"MockBank unavailable: {exc}") from exc

    balance = db.query(Balance).filter(Balance.user_id == user_id).first()
    if balance:
        balance.current_balance = balance_data.get("current_balance", balance.current_balance)
        balance.available_balance = balance_data.get("available_balance", balance.available_balance)
        balance.last_updated = balance_data.get("last_updated", balance.last_updated)
    else:
        balance = Balance(
            user_id=user_id,
            current_balance=balance_data.get("current_balance", 0.0),
            available_balance=balance_data.get("available_balance", 0.0),
            last_updated=balance_data.get("last_updated"),
        )
        db.add(balance)
    db.commit()
    db.refresh(balance)
    return balance
