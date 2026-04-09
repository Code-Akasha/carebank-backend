from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.account import Account
from app.models.user import User
from app.schemas.models import AccountResponse
from app.services.banking_client import get_banking_client, BankingClientError

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreateRequest(BaseModel):
    account_type: str = Field(default="savings", min_length=3, max_length=40)
    name: str = Field(default="New Account", min_length=2, max_length=120)
    provider_id: str = Field(default="carebank_retail", min_length=2, max_length=80)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    initial_deposit: float = Field(default=0.0, ge=0.0)


def _persist_accounts(db: Session, records: list[dict]) -> None:
    if not records:
        return
    for record in records:
        account = (
            db.query(Account)
            .filter(Account.account_id == record.get("account_id"))
            .first()
        )
        if account:
            account.name = record.get("name", account.name)
            account.account_type = record.get("account_type", account.account_type)
            account.mask = record.get("mask", account.mask)
            account.currency = record.get("currency", account.currency)
            account.institution = record.get("institution", account.institution)
            account.current_balance = record.get(
                "current_balance", account.current_balance
            )
            account.available_balance = record.get(
                "available_balance", account.available_balance
            )
            account.status = record.get("status", account.status)
            account.provider_id = record.get("provider_id", account.provider_id)
            account.last_statement_date = record.get(
                "last_statement_date", account.last_statement_date
            )
        else:
            db.add(
                Account(
                    account_id=record.get("account_id"),
                    user_id=record.get("user_id"),
                    provider_id=record.get("provider_id"),
                    name=record.get("name", "Unknown Account"),
                    account_type=record.get("account_type", "checking"),
                    mask=record.get("mask"),
                    currency=record.get("currency"),
                    institution=record.get("institution"),
                    current_balance=record.get("current_balance", 0.0),
                    available_balance=record.get("available_balance", 0.0),
                    status=record.get("status", "active"),
                    last_statement_date=record.get("last_statement_date"),
                )
            )
    db.commit()


@router.get("/", response_model=list[AccountResponse])
async def list_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    client = get_banking_client()
    try:
        records = await client.get_accounts(current_user.user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc

    _persist_accounts(db, records)
    return records


@router.post("/", response_model=AccountResponse)
async def create_account(
    body: AccountCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    client = get_banking_client()
    payload = body.model_dump()
    payload["currency"] = body.currency.upper()
    try:
        response = await client.create_account(current_user.user_id, payload)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(
            status_code=status_code,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    created_account = response.get("account") if isinstance(response, dict) else None
    if not isinstance(created_account, dict):
        raise HTTPException(
            status_code=502,
            detail="Unexpected response from banking provider while creating account",
        )

    _persist_accounts(db, [created_account])
    return created_account
