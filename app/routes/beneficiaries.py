"""Beneficiary management API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
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
    db: Session = Depends(get_db),
):
    """Create a new beneficiary (saved contact) in the connected banking provider."""
    # 1. Save beneficiary to local SQLite DB first to obtain an integer ID
    nickname = payload.nickname or payload.name
    rail = payload.payment_rail.upper()
    identifier_type = "upi_id" if rail == "UPI" else "account_number"
    identifier_value = payload.upi_handle if rail == "UPI" else payload.account_number

    from app.models.beneficiary import Beneficiary
    from app.schemas.payments import BeneficiaryCreate
    from app.services.beneficiary_service import create_beneficiary

    # Check if already exists in local DB
    db_beneficiary = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.user_id == current_user.user_id,
            Beneficiary.identifier_type == identifier_type,
            Beneficiary.identifier_value == identifier_value,
        )
        .first()
    )

    if not db_beneficiary:
        benef_create = BeneficiaryCreate(
            nickname=nickname,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            category=payload.nickname or "custom",
        )
        db_beneficiary = create_beneficiary(db, current_user.user_id, benef_create)

    # 2. Call banking provider to save to MockBank using the local DB ID as beneficiary_id
    client = get_banking_client()
    mockbank_payload = payload.model_dump(exclude_none=True)
    mockbank_payload["beneficiary_id"] = str(db_beneficiary.id)

    try:
        result = await client.create_beneficiary(
            current_user.user_id,
            mockbank_payload,
        )
    except BankingClientError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    # Return local DB ID instead of MockBank's string ID
    result["id"] = db_beneficiary.id
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
