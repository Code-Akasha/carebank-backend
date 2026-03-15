from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.profile import (
    PersistentExpenseItem,
    UserProfileResponse,
    UserProfileUpsertRequest,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _to_response(user_id: str, profile: UserProfile | None) -> UserProfileResponse:
    if not profile:
        expenses: list[PersistentExpenseItem] = []
        monthly_salary = 0.0
        currency = "INR"
        min_safe_balance = 5000.0
        savings_goal_pct = 0.2
        risk_tolerance = "moderate"
        notes = None
    else:
        expenses = [
            PersistentExpenseItem.model_validate(item)
            for item in (profile.persistent_expenses_json or [])
        ]
        monthly_salary = float(profile.monthly_salary)
        currency = profile.currency
        min_safe_balance = float(profile.min_safe_balance)
        savings_goal_pct = float(profile.savings_goal_pct)
        risk_tolerance = profile.risk_tolerance
        notes = profile.notes

    total_persistent = round(sum(item.amount for item in expenses), 2)
    projected_free_cashflow = round(monthly_salary - total_persistent, 2)

    return UserProfileResponse(
        user_id=user_id,
        monthly_salary=monthly_salary,
        currency=currency,
        min_safe_balance=min_safe_balance,
        savings_goal_pct=savings_goal_pct,
        risk_tolerance=risk_tolerance,
        persistent_expenses=expenses,
        total_persistent_expenses=total_persistent,
        projected_free_cashflow=projected_free_cashflow,
        notes=notes,
    )


@router.get("", response_model=UserProfileResponse)
def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == current_user.user_id)
        .first()
    )
    return _to_response(current_user.user_id, profile)


@router.put("", response_model=UserProfileResponse)
def upsert_profile(
    body: UserProfileUpsertRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == current_user.user_id)
        .first()
    )

    expenses_json = [item.model_dump() for item in body.persistent_expenses]

    if profile is None:
        profile = UserProfile(
            user_id=current_user.user_id,
            monthly_salary=body.monthly_salary,
            currency=body.currency.upper(),
            min_safe_balance=body.min_safe_balance,
            savings_goal_pct=body.savings_goal_pct,
            risk_tolerance=body.risk_tolerance,
            persistent_expenses_json=expenses_json,
            notes=body.notes,
        )
        db.add(profile)
    else:
        profile.monthly_salary = body.monthly_salary
        profile.currency = body.currency.upper()
        profile.min_safe_balance = body.min_safe_balance
        profile.savings_goal_pct = body.savings_goal_pct
        profile.risk_tolerance = body.risk_tolerance
        profile.persistent_expenses_json = expenses_json
        profile.notes = body.notes

    db.commit()
    db.refresh(profile)

    return _to_response(current_user.user_id, profile)
