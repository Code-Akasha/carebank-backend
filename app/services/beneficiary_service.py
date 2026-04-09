"""Beneficiary management service."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.beneficiary import Beneficiary
from app.schemas.payments import BeneficiaryCreate, BeneficiaryUpdate


def create_beneficiary(
    db: Session,
    user_id: str,
    body: BeneficiaryCreate,
) -> Beneficiary:
    """Create a new beneficiary for the user."""
    # Check if beneficiary with same identifier already exists
    existing = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.user_id == user_id,
            Beneficiary.identifier_type == body.identifier_type,
            Beneficiary.identifier_value == body.identifier_value,
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
        nickname=body.nickname,
        identifier_type=body.identifier_type,
        identifier_value=body.identifier_value,
        category=body.category,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def get_beneficiary(
    db: Session,
    user_id: str,
    beneficiary_id: int,
) -> Beneficiary:
    """Get a specific beneficiary."""
    beneficiary = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.id == beneficiary_id,
            Beneficiary.user_id == user_id,
        )
        .first()
    )
    if not beneficiary:
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
    user_id: str,
    beneficiary_id: int,
    body: BeneficiaryUpdate,
) -> Beneficiary:
    """Update a beneficiary."""
    beneficiary = get_beneficiary(db, user_id, beneficiary_id)

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
    user_id: str,
    beneficiary_id: int,
) -> None:
    """Delete a beneficiary."""
    beneficiary = get_beneficiary(db, user_id, beneficiary_id)
    db.delete(beneficiary)
    db.commit()


def verify_beneficiary(
    db: Session,
    user_id: str,
    beneficiary_id: int,
    verification_method: str = "otp",
) -> Beneficiary:
    """Mark a beneficiary as verified."""
    beneficiary = get_beneficiary(db, user_id, beneficiary_id)

    if beneficiary.is_verified:
        raise HTTPException(
            status_code=400,
            detail="Beneficiary already verified",
        )

    # In a real system, this would trigger OTP/micro-deposit verification
    # For now, mark as verified immediately
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
