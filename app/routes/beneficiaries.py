"""Beneficiary management API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.banking_client import BankingClientError, get_banking_client

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"])


class BeneficiaryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    payment_rail: str = Field(default="UPI", min_length=3, max_length=20)
    account_number: str | None = None
    ifsc: str | None = None
    upi_handle: str | None = None
    nickname: str | None = None


def _unwrap_beneficiary(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        nested = payload.get("beneficiary")
        if isinstance(nested, dict):
            return nested
        return payload
    return {}


@router.post("/")
async def create_beneficiary_endpoint(
    payload: BeneficiaryCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new beneficiary (saved contact) in the connected banking provider."""
    client = get_banking_client()
    try:
        result = await client.create_beneficiary(
            current_user.user_id,
            payload.model_dump(exclude_none=True),
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return result


@router.get("/")
async def list_beneficiaries_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all beneficiaries for current user."""
    client = get_banking_client()
    try:
        result = await client.get_beneficiaries(current_user.user_id)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return result if isinstance(result, list) else []


@router.get("/{beneficiary_id}")
async def get_beneficiary_endpoint(
    beneficiary_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get specific beneficiary details."""
    client = get_banking_client()
    try:
        result = await client.get_beneficiaries(current_user.user_id)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    for beneficiary in result if isinstance(result, list) else []:
        if str(beneficiary.get("id")) == str(beneficiary_id):
            return beneficiary

    raise HTTPException(status_code=404, detail="Beneficiary not found")


@router.put("/{beneficiary_id}")
async def update_beneficiary_endpoint(
    beneficiary_id: str,
    payload: BeneficiaryCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update beneficiary.

    MockBank currently does not expose a dedicated update endpoint.
    """
    _ = beneficiary_id
    _ = payload
    _ = current_user
    raise HTTPException(
        status_code=405,
        detail="Beneficiary update is not supported by the connected banking provider",
    )


@router.delete("/{beneficiary_id}")
async def delete_beneficiary_endpoint(
    beneficiary_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete a beneficiary.

    MockBank currently does not expose a dedicated delete endpoint.
    """
    _ = beneficiary_id
    _ = current_user
    raise HTTPException(
        status_code=405,
        detail="Beneficiary delete is not supported by the connected banking provider",
    )


@router.post("/{beneficiary_id}/verify")
@router.put("/{beneficiary_id}/verify")
async def verify_beneficiary_endpoint(
    beneficiary_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Mark beneficiary as verified."""
    client = get_banking_client()
    try:
        result = await client.verify_beneficiary(current_user.user_id, beneficiary_id)
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return result
