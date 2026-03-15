from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"])


class BeneficiaryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    payment_rail: str = Field(default="UPI", min_length=3, max_length=10)
    account_number: str | None = None
    ifsc: str | None = None
    upi_handle: str | None = None
    nickname: str | None = None


@router.get("/")
async def list_beneficiaries(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    client = get_banking_client()
    try:
        return await client.get_beneficiaries(current_user.user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc


@router.post("/")
async def create_beneficiary(
    body: BeneficiaryCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    client = get_banking_client()
    try:
        return await client.create_beneficiary(
            current_user.user_id,
            body.model_dump(),
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.put("/{beneficiary_id}/verify")
async def verify_beneficiary(
    beneficiary_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    client = get_banking_client()
    try:
        return await client.verify_beneficiary(current_user.user_id, beneficiary_id)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
