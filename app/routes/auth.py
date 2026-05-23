from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.admin_action_log import AdminActionLog
from app.models.beneficiary import Beneficiary
from app.models.business_profile import BusinessProfile
from app.models.user import User
from app.services.banking_client import get_banking_client
from app.services.mpin_service import set_mpin

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone_number: str | None = None
    account_type: str = "personal"  # "personal" or "business"
    # Business-specific fields (required when account_type="business")
    business_name: str | None = None
    business_category: str | None = None
    business_description: str | None = None


class BootstrapSuperAdminRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone_number: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    account_type: str = "personal"
    is_active: bool


class SetMPINRequest(BaseModel):
    mpin: str
    confirm_mpin: str


class SetMPINResponse(BaseModel):
    user_id: str
    mpin_set: bool = True


def _generate_user_id(db: Session) -> str:
    for _ in range(10):
        candidate = f"user_{uuid4().hex[:8]}"
        existing = db.query(User).filter(User.user_id == candidate).first()
        if not existing:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique user ID",
    )


def _has_admin_user(db: Session) -> bool:
    return db.query(User).filter(User.role == "admin").first() is not None


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
)
async def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered",
        )

    # Validate business fields
    acct_type = (body.account_type or "personal").strip().lower()
    if acct_type not in {"personal", "business"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_type must be 'personal' or 'business'",
        )
    if acct_type == "business":
        if not body.business_name or not body.business_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="business_name and business_category are required for business accounts",
            )

    # Determine role from account type
    role = "business" if acct_type == "business" else "user"
    user_id = _generate_user_id(db)

    user = User(
        user_id=user_id,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=role,
        account_type=acct_type,
        phone_number=body.phone_number,
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Create business profile if business account
    if acct_type == "business":
        biz_profile = BusinessProfile(
            user_id=user_id,
            business_name=body.business_name,
            category=body.business_category,
            description=body.business_description,
        )
        db.add(biz_profile)

        # Auto-create a global beneficiary so users can find and pay this business
        beneficiary = Beneficiary(
            user_id=user_id,  # Owned by the business itself for self-reference
            nickname=body.business_name,
            identifier_type="account_number",
            identifier_value=user_id,
            category=body.business_category,
            is_verified=True,
            is_trusted=True,
            linked_carebank_user_id=user_id,
        )
        db.add(beneficiary)

    db.commit()
    db.refresh(user)

    # Seed proxy profile
    try:
        client = get_banking_client()
        await client.create_profile(user_id, balance=25000.0)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Proxy profile seeding failed for %s (non-fatal): %s", user_id, exc,
        )

    token = create_access_token(
        {"user_id": user.user_id, "email": user.email, "role": user.role},
    )
    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        full_name=user.full_name,
    )


@router.post(
    "/bootstrap-super-admin",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_super_admin(
    body: BootstrapSuperAdminRequest,
    db: Session = Depends(get_db),
):
    if _has_admin_user(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Super admin already exists",
        )

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered",
        )

    user_id = _generate_user_id(db)
    user = User(
        user_id=user_id,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role="admin",
        account_type="personal",
        phone_number=body.phone_number,
        is_active=True,
    )
    db.add(user)

    db.add(
        AdminActionLog(
            admin_user_id=user_id,
            action_type="bootstrap_super_admin",
            resource_type="user",
            resource_id=user_id,
            environment=None,
            before_value=None,
            after_value=f"email={body.email}, role=admin, full_name={body.full_name}",
            status="success",
        ),
    )
    db.commit()
    db.refresh(user)

    try:
        client = get_banking_client()
        await client.create_profile(user_id, balance=25000.0)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Proxy profile seeding failed for bootstrap admin %s (non-fatal): %s",
            user_id,
            exc,
        )

    token = create_access_token(
        {"user_id": user.user_id, "email": user.email, "role": user.role},
    )
    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated",
        )

    token = create_access_token(
        {"user_id": user.user_id, "email": user.email, "role": user.role},
    )
    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        account_type=current_user.account_type,
        is_active=current_user.is_active,
    )


@router.patch("/phone")
async def update_phone(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update phone number (stored as unverified for hackathon)."""
    phone = (body.get("phone_number") or "").strip()
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="phone_number is required",
        )
    current_user.phone_number = phone
    current_user.phone_verified = False
    db.commit()
    return {
        "user_id": current_user.user_id,
        "phone_number": phone,
        "phone_verified": False,
    }


@router.post("/mpin/set", response_model=SetMPINResponse)
async def set_user_mpin(
    body: SetMPINRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.mpin != body.confirm_mpin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPIN confirmation does not match",
        )

    set_mpin(db=db, current_user=current_user, mpin=body.mpin)
    return SetMPINResponse(user_id=current_user.user_id)
