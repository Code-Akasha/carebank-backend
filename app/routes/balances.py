from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.balance import Balance
from app.models.user import User
from app.schemas.models import BalanceResponse
from app.services.banking_client import get_banking_client, BankingClientError

router = APIRouter(prefix="/api/balances", tags=["balances"])


@router.get("/", response_model=BalanceResponse)
async def get_balance(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    client = get_banking_client()
    try:
        balance_data = await client.get_balance(current_user.user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc

    balance = db.query(Balance).filter(Balance.user_id == current_user.user_id).first()
    if balance:
        balance.current_balance = balance_data.get(
            "current_balance", balance.current_balance
        )
        balance.available_balance = balance_data.get(
            "available_balance", balance.available_balance
        )
        balance.last_updated = balance_data.get("last_updated", balance.last_updated)
    else:
        balance = Balance(
            user_id=current_user.user_id,
            current_balance=balance_data.get("current_balance", 0.0),
            available_balance=balance_data.get("available_balance", 0.0),
            last_updated=balance_data.get("last_updated"),
        )
        db.add(balance)
    db.commit()
    db.refresh(balance)
    return balance
