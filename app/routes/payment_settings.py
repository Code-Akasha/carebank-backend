"""Payment settings management API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.payments import (
    PaymentSettingsResponse,
    PaymentSettingsUpdate,
    SetMPINRequest,
)
from app.services.payment_settings_service import (
    get_payment_settings,
    update_payment_settings,
    set_mpin,
)

router = APIRouter(prefix="/api/payment-settings", tags=["payment-settings"])


@router.get("/", response_model=PaymentSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's payment settings."""
    settings = get_payment_settings(db, current_user.user_id)
    return PaymentSettingsResponse.model_validate(settings)


@router.put("/", response_model=PaymentSettingsResponse)
async def update_settings(
    payload: PaymentSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update payment settings (thresholds, limits, auto-approval)."""
    settings = update_payment_settings(db, current_user.user_id, payload)
    return PaymentSettingsResponse.model_validate(settings)


@router.post("/mpin")
async def configure_mpin(
    payload: SetMPINRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or update MPIN for payment confirmation.

    MPIN must be 4-6 digits.
    """
    set_mpin(db, current_user.user_id, payload)
    return {"message": "MPIN configured successfully"}
