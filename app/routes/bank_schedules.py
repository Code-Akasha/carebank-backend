from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/bank-schedules", tags=["bank-schedules"])


class BankScheduleCreateRequest(BaseModel):
    action_type: str = Field(default="pay_bill", min_length=3, max_length=50)
    amount: float = Field(gt=0)
    merchant: str = Field(default="Scheduled Payment", min_length=2, max_length=120)
    category: str = Field(default="utilities", min_length=2, max_length=60)
    description: str | None = None
    payment_rail: str | None = None
    beneficiary_id: str | None = None
    beneficiary_verified: bool = True
    frequency: str = "monthly"
    day_of_month: int = Field(default=1, ge=1, le=31)
    start_date: date | None = None
    metadata: dict | None = None


@router.get("/settlement-windows")
async def get_settlement_windows(
    current_user: Annotated[User, Depends(get_current_user)],
    for_date: date | None = None,
) -> dict:
    client = get_banking_client()
    try:
        return await client.get_settlement_windows(
            current_user.user_id,
            for_date=for_date,
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/")
async def list_bank_schedules(
    current_user: Annotated[User, Depends(get_current_user)],
    include_inactive: bool = False,
) -> list[dict]:
    client = get_banking_client()
    try:
        return await client.get_schedules(
            current_user.user_id,
            include_inactive=include_inactive,
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/")
async def create_bank_schedule(
    body: BankScheduleCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    client = get_banking_client()
    payload = body.model_dump(exclude_none=True)
    try:
        return await client.create_schedule(current_user.user_id, payload)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/{schedule_id}/run")
async def run_bank_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    force: bool = False,
) -> dict:
    client = get_banking_client()
    try:
        return await client.run_schedule(
            current_user.user_id,
            schedule_id,
            force=force,
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/{schedule_id}")
async def cancel_bank_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    client = get_banking_client()
    try:
        return await client.cancel_schedule(current_user.user_id, schedule_id)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
