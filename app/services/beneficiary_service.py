"""Beneficiary management service."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.beneficiary import Beneficiary
from app.schemas.payments import BeneficiaryCreate, BeneficiaryUpdate


def _legacy_beneficiary_payload(**kwargs: Any) -> dict[str, Any]:
    if not kwargs:
        return {}
    if "body" in kwargs and isinstance(kwargs["body"], BeneficiaryCreate):
        body = kwargs["body"]
        return body.model_dump()

    name = kwargs.get("name") or kwargs.get("nickname")
    phone = kwargs.get("phone")
    upi = kwargs.get("upi") or kwargs.get("upi_handle")
    account_number = kwargs.get("account_number")
    ifsc = kwargs.get("ifsc")

    identifier_type = kwargs.get("identifier_type")
    identifier_value = kwargs.get("identifier_value")
    if not identifier_type or not identifier_value:
        if upi:
            identifier_type = "upi_id"
            identifier_value = upi
        elif account_number:
            identifier_type = "account_number"
            identifier_value = account_number
        elif phone:
            identifier_type = "phone"
            identifier_value = phone

    return {
        "nickname": name,
        "identifier_type": identifier_type,
        "identifier_value": identifier_value,
        "category": kwargs.get("category"),
        "ifsc": ifsc,
        "phone": phone,
        "upi": upi,
    }


def create_beneficiary(
    db: Session,
    user_id: str,
    body: BeneficiaryCreate | None = None,
    **legacy_kwargs: Any,
) -> Beneficiary:
    """Create a new beneficiary for the user."""
    payload = body.model_dump() if isinstance(body, BeneficiaryCreate) else _legacy_beneficiary_payload(**legacy_kwargs)
    if not payload.get("nickname"):
        return None
    if not payload.get("identifier_type") or not payload.get("identifier_value"):
        return None

    # Check if beneficiary with same identifier already exists
    existing = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.user_id == user_id,
            Beneficiary.identifier_type == payload["identifier_type"],
            Beneficiary.identifier_value == payload["identifier_value"],
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Beneficiary {body.identifier_value} already exists",
        )

    beneficiary = Beneficiary(
        user_id=user_id,
        nickname=payload["nickname"],
        identifier_type=payload["identifier_type"],
        identifier_value=payload["identifier_value"],
        phone_number=payload.get("phone"),
        upi_handle=payload.get("upi"),
        category=payload.get("category"),
        ifsc=payload.get("ifsc"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def get_beneficiary(
    db: Session,
    beneficiary_id: int,
    user_id: str | None = None,
) -> Beneficiary:
    """Get a specific beneficiary."""
    query = (
        db.query(Beneficiary)
        .filter(Beneficiary.id == beneficiary_id)
    )
    if user_id is not None:
        query = query.filter(Beneficiary.user_id == user_id)
    beneficiary = query.first()
    if not beneficiary:
        if user_id is None:
            return None
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return beneficiary


def list_beneficiaries(
    db: Session,
    user_id: str,
    category: str | None = None,
) -> list[Beneficiary]:
    """List all beneficiaries for the user."""
    query = db.query(Beneficiary).filter(Beneficiary.user_id == user_id)
    if category:
        query = query.filter(Beneficiary.category == category)
    return query.order_by(Beneficiary.last_used_at.desc()).all()


def update_beneficiary(
    db: Session,
    beneficiary_id: int,
    user_id: str | None = None,
    body: BeneficiaryUpdate | None = None,
    **legacy_kwargs: Any,
) -> Beneficiary:
    """Update a beneficiary."""
    beneficiary = get_beneficiary(db, beneficiary_id, user_id)

    if body is None:
        body = BeneficiaryUpdate(
            nickname=legacy_kwargs.get("name") or legacy_kwargs.get("nickname"),
            is_trusted=legacy_kwargs.get("is_trusted"),
            category=legacy_kwargs.get("category"),
        )

    if body.nickname is not None:
        beneficiary.nickname = body.nickname
    if body.category is not None:
        beneficiary.category = body.category
    if body.is_trusted is not None:
        beneficiary.is_trusted = body.is_trusted

    beneficiary.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def delete_beneficiary(
    db: Session,
    beneficiary_id: int,
    user_id: str | None = None,
) -> None:
    """Delete a beneficiary."""
    beneficiary = get_beneficiary(db, beneficiary_id, user_id)
    db.delete(beneficiary)
    db.commit()
    return True


def verify_beneficiary(
    db: Session,
    beneficiary_id: int,
    user_id: str | None = None,
    verification_method: str = "otp",
) -> Beneficiary:
    """Mark a beneficiary as verified."""
    beneficiary = get_beneficiary(db, beneficiary_id, user_id)

    beneficiary.is_verified = True
    beneficiary.verification_method = verification_method
    beneficiary.verified_at = datetime.now(timezone.utc)
    beneficiary.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def record_payment_to_beneficiary(
    db: Session,
    beneficiary_id: int,
    user_id: str | None = None,
) -> None:
    """Record that a payment was made to this beneficiary (for stats)."""
    query = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id)
    if user_id is not None:
        query = query.filter(Beneficiary.user_id == user_id)
    beneficiary = query.first()
    if beneficiary:
        beneficiary.payment_count += 1
        beneficiary.last_used_at = datetime.now(timezone.utc)
        beneficiary.updated_at = datetime.now(timezone.utc)
        db.commit()
