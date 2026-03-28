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
from app.models.user import User
from app.services.banking_client import get_banking_client
from app.services.mpin_service import set_mpin

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


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


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user_id = _generate_user_id(db)

    user = User(
        user_id=user_id,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        client = get_banking_client()
        await client.create_profile(user_id, balance=25000.0)
    except Exception:
        pass

    token = create_access_token(
        {"user_id": user.user_id, "email": user.email, "role": user.role}
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    token = create_access_token(
        {"user_id": user.user_id, "email": user.email, "role": user.role}
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
        is_active=current_user.is_active,
    )


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
